"""Private portable snapshots and verified restore into a new data directory."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import tempfile
import zipfile

from runner.io import read_json, sha_file, write_json
from service import APP_VERSION
from service.imports import safe_id, validate_archive_entries, remap_report, validated_report
from service.publication import public_bytes
from service.replays import from_bytes
from service.store import Store, utc_now

MAX_FILES = 50000
MAX_TOTAL = 2 * 1024**3
MAX_FILE = 64 * 1024**2
KINDS = {"session", "submission", "entrant", "job", "match", "tournament", "publication"}
ROOT_EXCLUSIONS = {"arena.sqlite3", "arena.sqlite3-wal", "arena.sqlite3-shm", "owner.token", "worker.lock", "backups"}


def references(records):
    """Only registered operational paths move; forensic JSON/text is unchanged."""
    fields = {"submission": ("source", "wasm"), "entrant": ("wasm",),
              "match": ("replay", "projection", "live_path"), "tournament": ("directory",), "publication": ("directory",)}
    for record in records:
        kind, row = record["kind"], record["value"]
        for key in fields.get(kind, ()):
            if row.get(key):
                yield record, [key], row[key], "directory" if key == "directory" else "file"
        if kind == "job":
            inputs = row["inputs"]
            if inputs.get("archive"):
                yield record, ["inputs", "archive"], inputs["archive"], "file"
            for i, entrant in enumerate(inputs.get("entrants", [])):
                yield record, ["inputs", "entrants", i, "wasm"], entrant["wasm"], "file"


def set_pointer(value, pointer, path):
    target = value
    for key in pointer[:-1]:
        target = target[key]
    target[pointer[-1]] = str(path)


def create_backup(store, *, output=None, current_job=None, offline=False):
    identity = "backup-" + secrets.token_hex(12)
    output = Path(output).resolve() if output else store.root / "backups" / f"{identity}.zip"
    if output.exists():
        raise FileExistsError("Backup output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT kind,body,updated FROM records ORDER BY kind,id").fetchall()
            records = [dict(kind=r["kind"], value=json.loads(r["body"]), updated=r["updated"]) for r in rows if r["kind"] in KINDS]
            backup_jobs = {r["value"]["id"] for r in records if r["kind"] == "job" and r["value"]["kind"] == "backup"}
            if not offline and any(r["kind"] == "job" and r["value"]["id"] != current_job
                                   and r["value"]["status"] in ("running", "stop_requested") for r in records):
                raise FileExistsError("Wait for the running computation before creating a backup")
            records = [r for r in records if not (r["kind"] == "job" and r["value"]["id"] in backup_jobs)]
            verify_restored_records(records)
            refs = list(references(records))
            external_dirs = []
            for _, _, path, kind in sorted(refs, key=lambda r: len(Path(r[2]).parts)):
                path = Path(path).resolve()
                if kind == "directory" and not path.is_relative_to(store.root) and not any(path.is_relative_to(p) for p in external_dirs):
                    external_dirs.append(path)
            def portable(path):
                path = Path(path).resolve()
                if path.is_relative_to(store.root):
                    return "data/" + path.relative_to(store.root).as_posix()
                for folder in external_dirs:
                    if path.is_relative_to(folder):
                        prefix = hashlib.sha256(str(folder).encode()).hexdigest()[:24]
                        relative = path.relative_to(folder).as_posix()
                        return f"data/_external_dirs/{prefix}" + ("/" + relative if relative != "." else "")
                suffix = path.suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", path.suffix) else ""
                return f"data/_external/{sha_file(path)}{suffix}"
            ref_rows = []
            for record, pointer, raw, kind in refs:
                path = Path(raw).resolve()
                if not path.exists() or (kind == "file" and not path.is_file()) or (kind == "directory" and not path.is_dir()):
                    raise ValueError("Registered evidence is missing; backup cannot claim completeness")
                ref_rows.append(dict(kind=record["kind"], id=record["value"]["id"], pointer=pointer, type=kind, archive_path=portable(path)))
            candidates = {}
            for root in [store.root, *external_dirs]:
                for path in root.rglob("*"):
                    if root == store.root:
                        relative = path.relative_to(root)
                        if relative.parts[0].casefold() in ROOT_EXCLUSIONS or (relative.parts[0] == "jobs" and len(relative.parts) > 1 and relative.parts[1] in backup_jobs):
                            continue
                    if path.is_symlink():
                        raise ValueError("Backup cannot follow symbolic links")
                    if path.is_file() and path.suffix != ".tmp":
                        candidates[portable(path)] = path
            for _, _, raw, kind in refs:
                if kind == "file":
                    candidates[portable(raw)] = Path(raw).resolve()
            if len(candidates) > MAX_FILES or sum(p.stat().st_size for p in candidates.values()) > MAX_TOTAL:
                raise ValueError("Private backup expansion limit exceeded")
            if any(p.stat().st_size > MAX_FILE for p in candidates.values()):
                raise ValueError("Private backup file limit exceeded")
            events = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id").fetchall()]
            descriptors = []
            total_size = 0
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name, path in sorted(candidates.items()):
                    hasher, size = hashlib.sha256(), 0
                    with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as destination:
                        while block := source.read(64*1024):
                            size += len(block)
                            total_size += len(block)
                            if size > MAX_FILE:
                                raise ValueError("Backup file grew beyond its limit")
                            if total_size > MAX_TOTAL:
                                raise ValueError("Backup files grew beyond the total expansion limit")
                            hasher.update(block)
                            destination.write(block)
                    checksum = hasher.hexdigest()
                    if sha_file(path) != checksum:
                        raise FileExistsError("Evidence changed during backup; retry after the operation finishes")
                    descriptors.append(dict(path=name, size=size, sha256=checksum))
                verify_captured_hashes(records, portable, descriptors)
                snapshot = dict(schema_version=1, kind="arena-private-backup", app_version=APP_VERSION, created=utc_now(),
                                origin_root=str(store.root), files=descriptors, records=records, references=ref_rows, events=events)
                metadata = public_bytes(snapshot)
                if len(metadata) > MAX_FILE:
                    raise ValueError("Private backup metadata limit exceeded")
                archive.writestr("snapshot.json", metadata)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    row = dict(id=identity, created=snapshot["created"], path=str(output), sha256=sha_file(output), size=output.stat().st_size,
               files=len(descriptors), records=len(records), contains_private_inputs=True)
    store.put("backup", row)
    return row


def verify_captured_hashes(records, portable, descriptors):
    """Bind the bytes actually archived to frozen metadata, even after a race."""
    copied = {entry["path"]: entry["sha256"] for entry in descriptors}
    def check(path, checksum):
        if copied.get(portable(path)) != checksum:
            raise ValueError("Archived bytes differ from frozen evidence; backup rejected")
    for record in records:
        kind, row = record["kind"], record["value"]
        if kind in ("submission", "entrant"):
            for field in ("source", "wasm"):
                if row.get(field):
                    check(row[field], row[field + "_sha256"])
        elif kind == "match" and row.get("replay"):
            check(row["replay"], row["source_sha256"])
        elif kind == "job":
            if row["inputs"].get("archive"):
                check(row["inputs"]["archive"], row["inputs"]["source_sha256"])
            for entrant in row["inputs"].get("entrants", []):
                check(entrant["wasm"], entrant["wasm_sha256"])
        elif kind == "publication":
            folder = Path(row["directory"])
            check(folder / "manifest.json", row["manifest_sha256"])
            for item in [row["manifest"]["report"], *row["manifest"]["matches"]]:
                check(folder / item["file"], item["public_sha256"])


def verify_restored_records(records, *, rebuild=False):
    for record in records:
        kind, row = record["kind"], record["value"]
        safe_id(row["id"])
        if kind in ("submission", "entrant"):
            for field in ("source", "wasm"):
                if row.get(field) and sha_file(row[field]) != row[field + "_sha256"]:
                    raise ValueError("Frozen source/WASM hash differs in backup")
        elif kind == "match" and row.get("replay"):
            if sha_file(row["replay"]) != row["source_sha256"]:
                raise ValueError("Original Replay hash differs in backup")
            ui = from_bytes(Path(row["replay"]).read_bytes())
            if ui["result"] != row["result"] or ui["verified"] != row["verified"]:
                raise ValueError("Match index differs from reconstructed Replay")
            if len(ui["entrants"]) != len(row["entrants"]):
                raise ValueError("Match identity count differs in backup")
            for entrant, frozen in zip(ui["entrants"], row["entrants"]):
                if entrant["wasm_sha256"] != frozen["wasm_sha256"]:
                    raise ValueError("Match identity hash differs in backup")
                entrant["id"] = frozen["id"]
            if rebuild and row.get("projection"):
                write_json(row["projection"], ui)  # Derived caches can be rebuilt; raw evidence stays byte-identical.
        elif kind == "job":
            if row["inputs"].get("archive") and sha_file(row["inputs"]["archive"]) != row["inputs"]["source_sha256"]:
                raise ValueError("Frozen uploaded archive differs in backup")
            for entrant in row["inputs"].get("entrants", []):
                if sha_file(entrant["wasm"]) != entrant["wasm_sha256"]:
                    raise ValueError("Frozen job artifact differs in backup")
        elif kind == "tournament" and row.get("directory"):
            report = remap_report(validated_report(Path(row["directory"])), row.get("entrant_aliases", {}))
            if row.get("report") and row["report"] != report:
                raise ValueError("Tournament index differs from verified evidence")
        elif kind == "publication":
            folder = Path(row["directory"])
            if sha_file(folder / "manifest.json") != row["manifest_sha256"] or read_json(folder / "manifest.json") != row["manifest"]:
                raise ValueError("Publication manifest differs in backup")
            for item in [row["manifest"]["report"], *row["manifest"]["matches"]]:
                name = item["file"]
                if Path(name).name != name or sha_file(folder / name) != item["public_sha256"]:
                    raise ValueError("Published copy differs in backup")


def restore_backup(archive_path, destination, *, expected_sha256=None):
    archive_path, destination = Path(archive_path).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("Restore requires a new directory; existing data is never overwritten")
    checksum = sha_file(archive_path)
    if archive_path.stat().st_size > MAX_TOTAL+MAX_FILE:
        raise ValueError("Private backup archive limit exceeded")
    if expected_sha256 and checksum != expected_sha256:
        raise ValueError("Private backup archive hash differs")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".arena-restore-", dir=destination.parent) as temporary:
        temporary = Path(temporary)
        data_root = temporary / "data"
        data_root.mkdir()
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = validate_archive_entries(archive, max_entries=MAX_FILES+1, max_total=MAX_TOTAL+MAX_FILE, max_entry=MAX_FILE)
                snapshot = json.loads(archive.read("snapshot.json"))
                if snapshot.get("schema_version") != 1 or snapshot.get("kind") != "arena-private-backup":
                    raise ValueError("Unsupported private backup schema")
                files = snapshot["files"]
                names = [f["path"] for f in files]
                if len(set(names)) != len(names) or set(i.filename for i in infos) != {"snapshot.json", *names}:
                    raise ValueError("Backup file index differs from archive")
                for entry in files:
                    name = PurePosixPath(entry["path"])
                    if name.parts[0] != "data" or len(name.parts) < 2 or name.parts[1].casefold() in ROOT_EXCLUSIONS:
                        raise ValueError("Unsafe private backup file role")
                    path = temporary.joinpath(*name.parts)
                    if not path.resolve().is_relative_to(data_root):
                        raise ValueError("Backup file escapes restore directory")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    hasher, size = hashlib.sha256(), 0
                    with archive.open(entry["path"]) as source, path.open("wb") as target:
                        while block := source.read(64*1024):
                            hasher.update(block); size += len(block); target.write(block)
                    if size != entry["size"] or hasher.hexdigest() != entry["sha256"]:
                        raise ValueError("Backup file hash/size differs")
                records = deepcopy(snapshot["records"])
                keys = [(r["kind"], r["value"]["id"]) for r in records]
                if len(set(keys)) != len(keys) or any(kind not in KINDS for kind, _ in keys):
                    raise ValueError("Invalid private backup record identities")
                ref_index = {(r["kind"], r["id"], tuple(r["pointer"])): r for r in snapshot["references"]}
                if len(ref_index) != len(snapshot["references"]):
                    raise ValueError("Duplicate private backup path references")
                found = set()
                for record, pointer, _, kind in list(references(records)):
                    key = (record["kind"], record["value"]["id"], tuple(pointer))
                    reference = ref_index[key]
                    name = PurePosixPath(reference["archive_path"])
                    path = temporary.joinpath(*name.parts).resolve()
                    if (name.parts[0] != "data" or not path.is_relative_to(data_root) or reference["type"] != kind
                            or (kind == "file" and not path.is_file()) or (kind == "directory" and not path.is_dir())):
                        raise ValueError("Invalid registered restore path")
                    set_pointer(record["value"], pointer, path)
                    found.add(key)
                if found != set(ref_index):
                    raise ValueError("Unknown backup path reference")
                verify_restored_records(records, rebuild=True)
                now = utc_now()
                interrupted = []
                for record in records:
                    row = record["value"]
                    if row.get("status") in ("queued", "running", "stop_requested", "compiling"):
                        row["status"] = "interrupted"
                        if record["kind"] == "job":
                            row["diagnostic"] = "Restored to a new local instance; resume explicitly after inspecting evidence."
                            interrupted.append(row["id"])
                            for attempt in row.get("attempts", []):
                                if not attempt.get("finished"):
                                    attempt.update(status="interrupted", finished=now)
                for record, pointer, raw, _ in list(references(records)):
                    set_pointer(record["value"], pointer, destination / Path(raw).relative_to(data_root))
                store = Store(data_root)  # New credentials; SQLite itself is never imported.
                with store.connection() as db:
                    for record in records:
                        db.execute("INSERT INTO records(kind,id,body,updated) VALUES (?,?,?,?)",
                                   (record["kind"], record["value"]["id"], json.dumps(record["value"], ensure_ascii=False, allow_nan=False), record["updated"]))
                    for event in snapshot["events"]:
                        db.execute("INSERT INTO events(id,resource,type,body,created) VALUES (?,?,?,?,?)",
                                   tuple(event[k] for k in ("id", "resource", "type", "body", "created")))
            # Same-volume rename after complete verification; no partial target is visible.
            if destination.exists():
                raise FileExistsError("Restore target was created during validation")
            data_root.rename(destination)
        except (zipfile.BadZipFile, KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Invalid private backup: {type(exc).__name__}") from exc
    return dict(status="restored", directory=str(destination), archive_sha256=checksum, files=len(files), records=len(records),
                interrupted_jobs=interrupted, credentials_rotated=True)


def main():
    parser = argparse.ArgumentParser(description="Private Arena data backup and new-directory recovery")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--data", required=True)
    create.add_argument("--output", required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("archive")
    restore.add_argument("--destination", required=True)
    restore.add_argument("--sha256")
    args = parser.parse_args()
    if args.command == "create":
        from service.jobs import Queue
        store = Store(args.data)
        queue = Queue(store)
        queue.lock_workspace()  # Offline creation cannot race a live service.
        try:
            result = create_backup(store, output=args.output, offline=True)
        finally:
            queue.stop()
    else:
        result = restore_backup(args.archive, args.destination, expected_sha256=args.sha256)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
