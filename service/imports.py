"""Bounded, atomic evidence import; original competition files stay unchanged."""
from copy import deepcopy
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from runner.io import ROOT, read_json, sha_file, write_json
from runner.report import generate_report
from replay.verify import read
from service.replays import from_bytes, MAX_REPLAY_BYTES
from service.store import utc_now

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("Evidence requires safe resource IDs")
    return value


def alias_id(identity, wasm_hash):
    return "i-" + wasm_hash[:16] + "-" + hashlib.sha256(identity.encode()).hexdigest()[:8]


def remap_report(report, aliases):
    report = deepcopy(report)
    for row in report.get("entrants", []):
        row["id"] = aliases.get(row["id"], row["id"])
    for row in report.get("pairs", []):
        for key in ("entrant", "opponent"):
            row[key] = aliases.get(row[key], row[key])
    return report


def validated_report(folder):
    """Reporter writes output; run it in a scratch copy, never in an archive."""
    folder = Path(folder)
    manifest = read_json(folder / "manifest.json")
    plan = read_json(folder / "schedule.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported tournament manifest schema")
    if not isinstance(plan, list) or len(plan) > 240000:
        raise ValueError("Tournament schedule limit exceeded")
    entrants = manifest.get("entrants", [])
    if not 2 <= len(entrants) <= 16 or len({e["id"] for e in entrants}) != len(entrants):
        raise ValueError("Tournament requires 2 to 16 distinct entrants")
    for entrant in entrants:
        safe_id(entrant["id"])
        if not re.fullmatch(r"[0-9a-f]{64}", entrant.get("wasm_sha256", "")):
            raise ValueError("Invalid entrant artifact hash")
    for item in plan:
        safe_id(item["match_id"])
    with tempfile.TemporaryDirectory(prefix="arena-report-") as scratch:
        scratch = Path(scratch)
        for name in ("manifest.json", "schedule.json", "cases.json", "results.jsonl"):
            path = folder / name
            if path.stat().st_size > MAX_EXPANDED_BYTES:
                raise ValueError("Tournament index file limit exceeded")
            shutil.copyfile(path, scratch / name)
        (scratch / "replays").mkdir()
        for item in plan:
            source = folder / "replays" / f"{item['match_id']}.jsonl"
            if source.is_file():
                if source.stat().st_size > MAX_REPLAY_BYTES:
                    raise ValueError("Replay exceeds 16 MiB")
                shutil.copyfile(source, scratch / "replays" / source.name)
        return generate_report(scratch)


def entrant_row(entrant, original_id=None):
    return dict(id=entrant["id"], name=original_id or entrant["id"], model=original_id or entrant["id"],
                original_id=original_id or entrant["id"], wasm_sha256=entrant["wasm_sha256"],
                status="historical", baseline=False, created=utc_now())


def register_entrant(store, value, db):
    try:
        previous = store.get("entrant", value["id"], db=db)
    except KeyError:
        store.put("entrant", value, create=True, db=db)
        return
    if previous["wasm_sha256"] != value["wasm_sha256"]:
        raise FileExistsError("Entrant ID already belongs to a different frozen WASM")
    if previous["status"] == "historical" and value["status"] == "qualified":
        previous.update(wasm=value["wasm"], status="qualified")
        store.put("entrant", previous, db=db)


def import_replay(store, data, *, title=None, tournament_id=None, identity=None, case=None,
                  disclosure="disclosed", attempt_id="imported", entrant_aliases=None, persist=True):
    ui = from_bytes(data)
    identity = safe_id(identity or "m-" + hashlib.sha256(data).hexdigest()[:20])
    aliases = dict(entrant_aliases or {})
    for entrant in ui["entrants"]:
        safe_id(entrant["id"])
        original = entrant["id"]
        if original not in aliases:
            try:
                existing = store.get("entrant", original)
                if existing["wasm_sha256"] != entrant["wasm_sha256"]:
                    aliases[original] = alias_id(original, entrant["wasm_sha256"])
            except KeyError:
                pass
        entrant["id"] = safe_id(aliases.get(original, original))
    folder = store.root / "matches" / identity / ui["source_sha256"][:16]
    folder.mkdir(parents=True, exist_ok=True)
    public_only = ui.get("verification") == "public_world_only"
    replay_path = folder / ("source-public.json" if public_only else "replay.jsonl")
    if replay_path.exists() and replay_path.read_bytes() != data:
        raise FileExistsError("Cannot replace frozen match evidence")
    replay_path.write_bytes(data)
    write_json(folder / "projection.json", ui)
    mapped_case = deepcopy(case)
    if mapped_case:
        for key in ("pair", "entrants"):
            mapped_case[key] = [aliases.get(eid, eid) for eid in mapped_case[key]]
    row = dict(id=identity, title=title or " × ".join(e["id"] for e in ui["entrants"]),
               tournament_id=tournament_id, entrants=ui["entrants"], status="completed" if ui["result"]["valid"] else "failed",
               ticks=len(ui["frames"])-1, result=ui["result"], verified=ui["verified"], disclosure=disclosure,
               replay=str(replay_path), projection=str(folder / "projection.json"), created=utc_now(),
               source_sha256=ui["source_sha256"], case=mapped_case, attempt_id=attempt_id)
    row.update(source_format="public_projection" if public_only else "raw_jsonl",
               origin_source_sha256=ui.get("origin_source_sha256"), bot_rerunnable=not public_only)
    row["facts"] = dict(moves=sum(e["type"] == "move" for f in ui["frames"] for e in f["events"]),
                        blocked_moves=sum(len(f["visual"]["blocked_moves"]) for f in ui["frames"]),
                        waits=sum(a["action"] == 0 for f in ui["frames"] for a in f["actions"]))
    if persist:
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = store.get("match", identity, db=db)
                if previous["status"] == "completed" and previous["source_sha256"] != ui["source_sha256"]:
                    raise FileExistsError("Cannot replace completed match evidence")
                row["created"] = previous["created"]
            except KeyError:
                pass
            for entrant in ui["entrants"]:
                original = next((k for k, v in aliases.items() if v == entrant["id"]), entrant["id"])
                register_entrant(store, entrant_row(entrant, original), db)
            store.put("match", row, db=db)
    return row


def validate_archive_entries(archive, *, max_entries=2000, max_total=MAX_EXPANDED_BYTES, max_entry=MAX_REPLAY_BYTES):
    infos = archive.infolist()
    if len(infos) > max_entries or sum(i.file_size for i in infos) > max_total:
        raise ValueError("Archive expansion limit exceeded")
    targets = {}
    for info in infos:
        if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError("Only unencrypted Stored/Deflate ZIP entries are supported")
        name = PurePosixPath(info.filename.replace("\\", "/"))
        if (name.is_absolute() or not name.parts or ".." in name.parts or ":" in str(name)
                or ((info.external_attr >> 16) & 0o170000) == 0o120000
                or any(p.endswith((".", " ")) or any(ord(c) < 32 or c in '<>"|?*' for c in p)
                       or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", p, re.I)
                       for p in name.parts)):
            raise ValueError("Unsafe archive path")
        key = str(name).casefold()
        if key in targets:
            raise ValueError("Duplicate or escaping archive path")
        if info.file_size > max_entry:
            raise ValueError("Archive entry limit exceeded")
        targets[key] = info
    for key, info in targets.items():
        for parent in PurePosixPath(key).parents:
            if str(parent) in targets and not targets[str(parent)].is_dir():
                raise ValueError("Archive file/directory collision")
    return infos


def extract_archive(path, destination):
    destination = Path(destination).resolve()
    if Path(path).stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds 16 MiB")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = validate_archive_entries(archive)
            for info in infos:
                target = destination.joinpath(*PurePosixPath(info.filename.replace("\\", "/")).parts)
                if not target.resolve().is_relative_to(destination):
                    raise ValueError("Archive path escapes import directory")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=64*1024)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError(f"Archive cannot be read: {type(exc).__name__}") from exc


def import_tournament(store, folder, identity, *, title="导入的比赛批次", source_hash=None, bundled=False):
    folder, identity = Path(folder), safe_id(identity)
    try:
        previous = store.get("tournament", identity)
        if previous.get("source_sha256") != source_hash:
            raise FileExistsError("Cannot replace imported tournament evidence")
        return previous
    except KeyError:
        pass
    report = validated_report(folder)
    manifest, plan = read_json(folder / "manifest.json"), read_json(folder / "schedule.json")
    aliases = {e["id"]: e["id"] if bundled else alias_id(e["id"], e["wasm_sha256"]) for e in manifest["entrants"]}
    row = dict(id=identity, title=title, status=report["status"], disclosure="disclosed" if bundled else "sealed", official=False,
               report=remap_report(report, aliases), expected_matches=len(plan), completed_matches=report.get("valid_matches", report.get("supplied_matches", 0)),
               manifest=manifest, entrant_aliases=aliases, directory=str(folder.resolve()), created=utc_now(),
               source_sha256=source_hash, imported=True, bundled_reference=bundled,
               requires_disclosure_confirmation=not bundled, submission_window_closed=False)
    matches, entrants = [], []
    results = {r["match_id"]: r for r in read(folder / "results.jsonl")}
    for item in plan:
        path = folder / "replays" / f"{item['match_id']}.jsonl"
        if item["match_id"] not in results:
            continue
        if not path.is_file():
            raise ValueError("Supplied match result is missing its Replay")
        data = path.read_bytes()
        records = [json.loads(line) for line in data.decode("utf-8-sig").splitlines() if line.strip()]
        header = records[0]
        artifacts = {e["id"]: e["wasm_sha256"] for e in manifest["entrants"]}
        if (header["match_id"] != item["match_id"] or header["components"] != manifest["components"]
                or header["rules"] != manifest["rules"] or header["budget"] != manifest["budget"]
                or header["map_seed"] != item["map_seed"] or header["bot_seeds"] != item["bot_seeds"]
                or header["entrants"] != [dict(id=eid, slot=i, wasm_sha256=artifacts[eid]) for i,eid in enumerate(item["entrants"])]
                or dict(records[-1], replay_sha256=sha_file(path)) != results[item["match_id"]]):
            raise ValueError("Replay/result differs from frozen tournament inputs")
        matches.append(import_replay(store, data, title=" × ".join(item["entrants"]), tournament_id=identity,
                                     identity=identity + "-" + item["match_id"], case=item,
                                     entrant_aliases=aliases, persist=False, disclosure=row["disclosure"]))
    for entrant in manifest["entrants"]:
        value = entrant_row(dict(id=aliases[entrant["id"]], wasm_sha256=entrant["wasm_sha256"]), entrant["id"])
        value["baseline"] = bundled
        wasm = folder / "build" / f"{entrant['id']}.wasm"
        if wasm.is_file():
            if sha_file(wasm) != entrant["wasm_sha256"]:
                raise ValueError("Archived WASM hash differs from frozen entrant")
            from runner.match import qualify
            from runtime.wasm import Backend
            with Backend() as backend:
                value["qualification"] = qualify(backend, wasm)
            value.update(wasm=str(wasm.resolve()), status="qualified")
        entrants.append(value)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        for entrant in entrants:
            register_entrant(store, entrant, db)
        for match in matches:
            store.put("match", match, create=True, db=db)
        store.put("tournament", row, create=True, db=db)
    store.emit(identity, "imported", dict(id=identity, status=row["status"]))
    return row


def import_uploaded_archive(store, path, source_hash, title):
    if sha_file(path) != source_hash:
        raise ValueError("Frozen upload changed")
    identity = "archive-" + source_hash[:20]
    try:
        return store.get("tournament", identity)
    except KeyError:
        pass
    folder = store.root / "imports" / identity
    extract_archive(path, folder)
    try:
        return import_tournament(store, folder, identity, title=title, source_hash=source_hash)
    except (KeyError, TypeError, IndexError, FileNotFoundError) as exc:
        raise ValueError(f"Tournament archive is incomplete or malformed: {type(exc).__name__}") from exc


def import_bundled(store):
    try:
        return store.get("tournament", "reference-v01")
    except KeyError:
        pass
    archive = ROOT / "artifacts/acceptance/v0.1-release/evidence.zip"
    expected = read_json(archive.with_name("evidence.index.json"))["sha256"]
    if sha_file(archive) != expected:
        raise ValueError("Bundled evidence checksum differs")
    folder = store.root / "imports/reference-v01"
    extract_archive(archive, folder)
    row = import_tournament(store, folder, "reference-v01", title="工程参考赛 · v0.1", source_hash=expected, bundled=True)
    path = folder / "examples/chain/replay.jsonl"
    if path.exists():
        import_replay(store, path.read_bytes(), title="连锁爆炸 · 同 Tick 平局", identity="reference-chain")
    return row
