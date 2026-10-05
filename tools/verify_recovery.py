"""Audit a downloaded private snapshot against its source and a fresh restore."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, sha_file, write_json
from service.backup import references, set_pointer
from service.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verify-existing", action="store_true", help="Audit a directory already restored by this tool; never overwrite it")
    args = parser.parse_args()
    source = Store(args.data)
    archive, destination = Path(args.archive).resolve(), Path(args.destination).resolve()
    digest = sha_file(archive)
    receipt = next(r for r in source.list("backup") if r["sha256"] == digest)
    command = [sys.executable, "-m", "service.backup", "restore", str(archive),
               "--destination", str(destination), "--sha256", receipt["sha256"]]
    started = time.monotonic()
    previous = None
    if args.verify_existing:
        previous = json.loads(Path(args.output).read_text(encoding="utf-8"))
        if previous.get("status") != "passed" or previous["archive_sha256"] != digest or not destination.is_dir():
            raise ValueError("Existing recovery has no matching successful receipt")
        restore_result = dict(interrupted_jobs=previous["interrupted_jobs"])
    else:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise ValueError(result.stderr)
        restore_result = json.loads(result.stdout)
    restored = Store(destination)
    if restored.token == source.token:
        raise ValueError("Recovery retained old credentials")
    with zipfile.ZipFile(archive) as bundle:
        snapshot = json.loads(bundle.read("snapshot.json"))
    mapping = {(r["kind"], r["id"], tuple(r["pointer"])): r for r in snapshot["references"]}
    cache_paths = {r["archive_path"] for r in snapshot["references"] if r["pointer"] == ["projection"]}
    raw_files = 0
    for file in snapshot["files"]:
        if file["path"] not in cache_paths:
            path = destination.joinpath(*Path(file["path"]).parts[1:])
            if path.stat().st_size != file["size"] or sha_file(path) != file["sha256"]:
                raise ValueError("Restored original bytes differ from the downloaded snapshot")
            raw_files += 1
    for record in snapshot["records"]:
        expected = deepcopy(record)
        for _, pointer, _, _ in list(references([expected])):
            reference = mapping[(record["kind"], record["value"]["id"], tuple(pointer))]
            set_pointer(expected["value"], pointer, destination.joinpath(*Path(reference["archive_path"]).parts[1:]))
        actual = restored.get(record["kind"], record["value"]["id"])
        if expected["value"].get("status") in ("queued", "running", "stop_requested", "compiling"):
            if actual["status"] != "interrupted":
                raise ValueError("Unfinished computation resumed automatically")
            # Recovery changes attempt diagnostics/timestamps, never frozen inputs.
            for field in ("inputs", "source_sha256", "entrants", "schedule_hash"):
                if actual.get(field) != expected["value"].get(field):
                    raise ValueError("Recovery changed unfinished frozen inputs")
        elif actual != expected["value"]:
            raise ValueError("Recovery changed completed metadata or closure/publication records")
    events = [dict(event_id=e["id"], resource_id=e["resource"], type=e["type"],
                   payload=json.loads(e["body"]), created=e["created"]) for e in snapshot["events"]]
    if restored.events(limit=len(events)+1) != events:
        raise ValueError("Restored event sequence differs")
    qualified = [s for s in restored.list("submission") if s["status"] == "qualified"]
    workflow = None
    for submitted in qualified:
        entrant_id = submitted["entrant_id"]
        single = next((m for m in restored.list("match") if not m.get("tournament_id") and
                       m["status"] == "completed" and any(e["id"] == entrant_id for e in m["entrants"])), None)
        batch = next((b for b in restored.list("tournament") if b.get("published_at") and
                      b.get("report", {}).get("status") == "complete" and
                      any(e["id"] == entrant_id for e in b["report"].get("entrants", []))), None)
        if single and batch:
            workflow = dict(submission_id=submitted["id"], entrant_id=entrant_id, match_id=single["id"],
                            tournament_id=batch["id"], publication_id=batch["publication_id"],
                            publication_sha256=batch["publication_sha256"],
                            source_sha256=submitted["source_sha256"], wasm_sha256=submitted["wasm_sha256"])
            break
    public = next(m for m in restored.list("match") if m.get("source_format") == "public_projection")
    if workflow is None:
        raise ValueError("Snapshot lacks the qualified-source/live-match/published-batch workflow")
    # Public proof contains identities/counts/hashes, never the private snapshot.
    proof = dict(status="passed", archive_sha256=digest, backup_id=receipt["id"],
                 restore_command=[sys.executable, "-m", "service.backup", "restore", args.archive,
                                  "--destination", args.destination, "--sha256", digest],
                 restore_exit_code=previous["restore_exit_code"] if previous else result.returncode,
                 elapsed_seconds=previous["elapsed_seconds"] if previous else round(time.monotonic()-started, 3),
                 platform=platform.platform(), files=receipt["files"], original_files_checked=raw_files,
                 rebuilt_projection_caches=len(cache_paths), metadata_records_checked=len(snapshot["records"]),
                 events_checked=len(events), credentials_rotated=True, workflow=workflow,
                 public_replay_id=public["id"], public_replay_source_sha256=public["source_sha256"],
                 interrupted_jobs=restore_result["interrupted_jobs"])
    write_json(args.output, proof)
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
