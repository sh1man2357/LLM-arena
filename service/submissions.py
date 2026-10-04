"""Exactly one frozen final submission per 60-minute development session."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets

from runner.io import ROOT, sha_file
from engine.model import digest
from service.store import utc_now


def parse_time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must contain a timezone")
    return result.astimezone(timezone.utc)


def session_view(value, now=None):
    result = dict(value)
    now = now or datetime.now(timezone.utc)
    if result["status"] == "open" and now > parse_time(result["deadline"]):
        result["status"] = "missing"
    return result


def create_session(store, name, model, started_at=None, time_source="host_confirmation", key=None):
    started = parse_time(started_at) if started_at else datetime.now(timezone.utc)
    if started > datetime.now(timezone.utc) + timedelta(seconds=5):
        raise ValueError("Session cannot start in the future")
    value = dict(id="s-" + secrets.token_hex(8), name=name, model=model, started_at=started.isoformat(),
                 deadline=(started + timedelta(minutes=60)).isoformat(), time_source=time_source,
                 task_sha256=sha_file(ROOT / "MODEL_TASK.md"), status="open", submission_id=None, created=utc_now())
    request_hash = digest(dict(name=name, model=model, started_at=started_at, time_source=time_source))
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if key:
            if len(key) > 128:
                raise ValueError("Idempotency key exceeds 128 characters")
            for existing in db.execute("SELECT body FROM records WHERE kind='session'").fetchall():
                previous = json.loads(existing["body"])
                if previous.get("key") == key:
                    if previous["request_hash"] != request_hash:
                        raise FileExistsError("Idempotency key has different session inputs")
                    return previous
        value.update(key=key, request_hash=request_hash)
        store.put("session", value, create=True, db=db)
    store.emit(value["id"], "session", dict(status="open"))
    return value


def submit(store, session_id, source, *, received_at=None):
    data = source.encode("utf-8")
    if not data or len(data) > 1024 * 1024:
        raise ValueError("Source must contain 1 byte to 1 MiB")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM records WHERE kind='session' AND id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(session_id)
        session = json.loads(row[0])
        if session["submission_id"]:
            frozen = db.execute("SELECT body FROM records WHERE kind='submission' AND id=?", (session["submission_id"],)).fetchone()
            previous = json.loads(frozen["body"])
            if previous["source_sha256"] == hashlib.sha256(data).hexdigest() and (not received_at or parse_time(received_at) == parse_time(previous["received_at"])):
                return previous
            raise FileExistsError("Final source is already frozen; it cannot be replaced")
        if received_at and session["time_source"] != "external_record":
            raise ValueError("Custom receipt times require an explicitly external time record")
        received = parse_time(received_at) if received_at else datetime.now(timezone.utc)
        if received < parse_time(session["started_at"]) or received > datetime.now(timezone.utc) + timedelta(seconds=5):
            raise ValueError("Invalid source receipt time")
        late = received > parse_time(session["deadline"])
        identity = "sub-" + secrets.token_hex(8)
        folder = store.root / "submissions" / identity
        folder.mkdir(parents=True)
        path = folder / "bot.cpp"
        path.write_bytes(data)
        value = dict(id=identity, session_id=session_id, name=session["name"], model=session["model"],
                     source=str(path), source_sha256=hashlib.sha256(data).hexdigest(), received_at=received.isoformat(),
                     frozen_at=utc_now(), time_source=session["time_source"], late=late,
                     status="late" if late else "submitted", created=utc_now())
        session.update(status="late" if late else "submitted", submission_id=identity, received_at=received.isoformat())
        store.put("submission", value, create=True, db=db)
        store.put("session", session, db=db)
    store.emit(session_id, "submitted", dict(id=identity, status=value["status"]))
    return value
