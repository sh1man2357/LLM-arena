"""Durable local metadata and event sequence; raw competition files stay separate."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sqlite3

from runner.io import write_json


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "arena.sqlite3"
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                    updated TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, resource TEXT NOT NULL,
                    type TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
        token = self.root / "owner.token"
        if not token.exists():
            token.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        self.token = token.read_text(encoding="utf-8")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, kind, identity, *, db=None):
        if db is None:
            with self.connection() as connection:
                return self.get(kind, identity, db=connection)
        row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, identity)).fetchone()
        if row is None:
            raise KeyError(identity)
        return json.loads(row["body"])

    def list(self, kind):
        with self.connection() as db:
            rows = db.execute("SELECT body FROM records WHERE kind=? ORDER BY updated DESC,id", (kind,)).fetchall()
        return [json.loads(r["body"]) for r in rows]

    def update(self, kind, identity, change):
        """Read-modify-write under one lock so concurrent progress cannot undo a stop or disclosure."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, identity)).fetchone()
            if row is None:
                raise KeyError(identity)
            value = json.loads(row["body"])
            change(value)
            self.put(kind, value, db=db)
        return value

    def put(self, kind, value, *, create=False, db=None):
        if db is None:
            with self.connection() as connection:
                return self.put(kind, value, create=create, db=connection)
        sql = ("INSERT INTO records(kind,id,body,updated) VALUES (?,?,?,?)" if create else
               "INSERT INTO records(kind,id,body,updated) VALUES (?,?,?,?) "
               "ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body,updated=excluded.updated")
        db.execute(sql, (kind, value["id"], json.dumps(value, ensure_ascii=False, allow_nan=False), utc_now()))
        return value

    def emit(self, resource, event_type, payload):
        with self.connection() as db:
            cursor = db.execute("INSERT INTO events(resource,type,body,created) VALUES (?,?,?,?)",
                                (resource, event_type, json.dumps(payload, ensure_ascii=False), utc_now()))
            return cursor.lastrowid

    def events(self, after=0, limit=100):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (after, limit)).fetchall()
        return [dict(event_id=r["id"], resource_id=r["resource"], type=r["type"], payload=json.loads(r["body"]),
                     created=r["created"]) for r in rows]

    def event_watermark(self):
        with self.connection() as db:
            return db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]

    def backup_metadata(self, output):
        with self.connection() as db:
            rows = db.execute("SELECT kind,id,body FROM records ORDER BY kind,id").fetchall()
        value = dict(schema_version=1, created=utc_now(), records=[dict(kind=r["kind"], value=json.loads(r["body"])) for r in rows])
        write_json(output, value)
        return value
