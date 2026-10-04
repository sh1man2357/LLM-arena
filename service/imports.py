"""Controlled evidence import. Never expose host paths in spectator responses."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from runner.io import ROOT, read_json, sha_file, write_json
from runner.report import generate_report
from replay.verify import read
from service.replays import from_bytes
from service.store import utc_now


def import_replay(store, data, *, title=None, tournament_id=None, identity=None, case=None):
    ui = from_bytes(data)
    identity = identity or "m-" + hashlib.sha256(data).hexdigest()[:20]
    folder = store.root / "matches" / identity
    folder.mkdir(parents=True, exist_ok=True)
    replay_path = folder / "replay.jsonl"
    if replay_path.exists() and replay_path.read_bytes() != data:
        raise ValueError("Cannot replace frozen match evidence")
    replay_path.write_bytes(data)
    write_json(folder / "projection.json", ui)
    row = dict(id=identity, title=title or " × ".join(e["id"] for e in ui["entrants"]),
               tournament_id=tournament_id, entrants=ui["entrants"], status="completed" if ui["result"]["valid"] else "failed",
               ticks=len(ui["frames"])-1, result=ui["result"], verified=ui["verified"], disclosure="disclosed",
               replay=str(replay_path), projection=str(folder / "projection.json"), created=utc_now(),
               source_sha256=ui["source_sha256"], case=case, attempt_id="imported")
    row["facts"] = dict(moves=sum(e["type"] == "move" for f in ui["frames"] for e in f["events"]),
                        blocked_moves=sum(len(f["visual"]["blocked_moves"]) for f in ui["frames"]),
                        waits=sum(a["action"] == 0 for f in ui["frames"] for a in f["actions"]))
    store.put("match", row)
    for entrant in ui["entrants"]:
        try:
            store.get("entrant", entrant["id"])
        except KeyError:
            store.put("entrant", dict(id=entrant["id"], name=entrant["id"], model=entrant["id"],
                                      wasm_sha256=entrant["wasm_sha256"], status="historical", baseline=False,
                                      created=utc_now()))
    return row


def extract_archive(path, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 2000 or sum(i.file_size for i in infos) > 256 * 1024 * 1024:
            raise ValueError("Archive expansion limit exceeded")
        for info in infos:
            name = PurePosixPath(info.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or ":" in str(name) or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Unsafe archive path")
            target = destination.joinpath(*name.parts).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Archive path escapes import directory")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                if info.file_size > 16 * 1024 * 1024:
                    raise ValueError("Archive entry limit exceeded")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))


def import_tournament(store, folder, identity, *, title="工程参考赛 · v0.1", source_hash=None):
    folder = Path(folder)
    report = generate_report(folder)
    manifest, plan = read_json(folder / "manifest.json"), read_json(folder / "schedule.json")
    row = dict(id=identity, title=title, status=report["status"], disclosure="disclosed", official=False,
               report=report, expected_matches=len(plan), completed_matches=report.get("valid_matches", 0),
               manifest=manifest, directory=str(folder.resolve()), created=utc_now(), source_sha256=source_hash)
    # Validate all authoritative evidence before inserting into the visible index.
    for item in plan:
        path = folder / "replays" / f"{item['match_id']}.jsonl"
        if path.exists():
            import_replay(store, path.read_bytes(), tournament_id=identity,
                          identity=identity + "-" + item["match_id"], case=item)
    for entrant in manifest["entrants"]:
        previous = store.get("entrant", entrant["id"])
        wasm = folder / "build" / f"{entrant['id']}.wasm"
        if wasm.exists() and sha_file(wasm) == entrant["wasm_sha256"]:
            previous.update(wasm=str(wasm.resolve()), status="qualified", baseline=True)
            store.put("entrant", previous)
    store.put("tournament", row)
    store.emit(identity, "imported", dict(id=identity, status=row["status"]))
    return row


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
    row = import_tournament(store, folder, "reference-v01", source_hash=expected)
    # A compact, genuinely chained explosion example is a useful first viewing.
    path = folder / "examples/chain/replay.jsonl"
    if path.exists():
        import_replay(store, path.read_bytes(), title="连锁爆炸 · 同 Tick 平局", identity="reference-chain")
    return row
