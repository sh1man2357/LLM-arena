"""Immutable public copies, linked to private evidence by hashes only."""
import hashlib
import json
from pathlib import Path
import secrets

from runner.io import sha_file
from service import APP_VERSION
from service.imports import validated_report, remap_report
from service.store import utc_now


def public_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def close_submissions(store, identity):
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = store.get("tournament", identity, db=db)
        if not row.get("official") and not row.get("requires_disclosure_confirmation"):
            raise FileExistsError("Public development batch has no hidden submission window")
        if row.get("submission_window_closed"):
            return row
        row.update(submission_window_closed=True, window_closed_at=utc_now(), disclosure="disclosed")
        if row.get("manifest"):
            pool = row["manifest"]["entrants"]
        else:
            pool = store.get("job", row["job_id"], db=db)["inputs"]["entrants"]
        aliases = row.get("entrant_aliases", {})
        row.update(window_close_source="host_confirmation", window_closed_entrants=[
            dict(id=aliases.get(e["id"], e["id"]), wasm_sha256=e["wasm_sha256"]) for e in pool])
        store.put("tournament", row, db=db)
        for entry in db.execute("SELECT body FROM records WHERE kind='match'").fetchall():
            match = json.loads(entry[0])
            if match.get("tournament_id") == identity:
                match["disclosure"] = "disclosed"
                store.put("match", match, db=db)
    store.emit(identity, "tournament", dict(disclosure="disclosed"))
    return row


def publish_tournament(store, identity):
    row = store.get("tournament", identity)
    if row.get("publication_id"):
        return row
    if row["status"] != "complete" or ((row.get("official") or row.get("requires_disclosure_confirmation")) and not row.get("submission_window_closed")):
        raise FileExistsError("Complete validation and close submissions before publication")
    folder = Path(row["directory"])
    report = remap_report(validated_report(folder), row.get("entrant_aliases", {}))
    if report["status"] != "complete":
        raise FileExistsError("Incomplete evidence cannot be published")
    matches = sorted([m for m in store.list("match") if m.get("tournament_id") == identity], key=lambda m: m["id"])
    if len(matches) != report["valid_matches"] or any(m["status"] != "completed" or not m["verified"] for m in matches):
        raise FileExistsError("Public match index differs from validated tournament")
    pid, published_at = "pub-" + secrets.token_hex(12), utc_now()
    destination = store.root / "publications" / pid
    destination.mkdir(parents=True)
    report_path = destination / "report.json"
    report_path.write_bytes(public_bytes(report))
    entries = []
    for match in matches:
        if sha_file(match["replay"]) != match["source_sha256"]:
            raise FileExistsError("Indexed Replay changed before publication")
        # Rebuild the public projection from immutable raw evidence. Do not trust
        # editable UI caches or allow them to inject private fields into exports.
        from service.replays import from_bytes
        ui = from_bytes(Path(match["replay"]).read_bytes())
        for entrant, frozen in zip(ui["entrants"], match["entrants"]):
            if entrant["wasm_sha256"] != frozen["wasm_sha256"]:
                raise FileExistsError("Public entrant artifact differs from raw Replay")
            entrant["id"] = frozen["id"]
        path = destination / f"{match['id']}.json"
        path.write_bytes(public_bytes(ui))
        entries.append(dict(id=match["id"], source_sha256=match["source_sha256"],
                            public_sha256=sha_file(path), file=path.name))
    manifest = dict(schema_version=1, app_version=APP_VERSION, publication_id=pid, tournament_id=identity,
                    published_at=published_at, window_closed_at=row.get("window_closed_at"),
                    window_close_source=row.get("window_close_source"), window_closed_entrants=row.get("window_closed_entrants"),
                    disclosure="archived", disclosed_fields=["map", "actions", "events", "results", "wasm_hashes"],
                    verification="world_verified; seed-free copies cannot rerun Bots",
                    source_manifest_sha256=sha_file(folder / "manifest.json"),
                    source_schedule_sha256=sha_file(folder / "schedule.json"),
                    source_results_sha256=sha_file(folder / "results.jsonl"),
                    report=dict(file="report.json", public_sha256=sha_file(report_path)), matches=entries)
    manifest_path = destination / "manifest.json"
    manifest_path.write_bytes(public_bytes(manifest))
    record = dict(id=pid, tournament_id=identity, manifest=manifest, manifest_sha256=sha_file(manifest_path),
                  directory=str(destination), created=published_at)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = store.get("tournament", identity, db=db)
        if current.get("publication_id"):
            return current
        if current["status"] != "complete" or ((current.get("official") or current.get("requires_disclosure_confirmation")) and not current.get("submission_window_closed")):
            raise FileExistsError("Tournament publication state changed")
        current.update(publication_id=pid, published_at=published_at, publication_sha256=record["manifest_sha256"],
                       disclosure="archived", report=report)
        store.put("publication", record, create=True, db=db)
        store.put("tournament", current, db=db)
        for match in matches:
            latest = store.get("match", match["id"], db=db)
            if latest["source_sha256"] != match["source_sha256"]:
                raise FileExistsError("Match changed during publication")
            latest.update(disclosure="archived", publication_id=pid)
            store.put("match", latest, db=db)
    store.emit(identity, "tournament", dict(status="published"))
    return current


def published_file(store, row, kind):
    publication = store.get("publication", row["publication_id"])
    if kind == "publication":
        name, expected = "manifest.json", publication["manifest_sha256"]
    elif kind == "report":
        descriptor = publication["manifest"]["report"]
        name, expected = descriptor["file"], descriptor["public_sha256"]
    else:
        descriptor = next(m for m in publication["manifest"]["matches"] if m["id"] == row["id"])
        name, expected = descriptor["file"], descriptor["public_sha256"]
    path = Path(publication["directory"]) / name
    if not path.is_file() or sha_file(path) != expected:
        raise FileExistsError("Archived public copy hash differs; restore from verified backup")
    return path
