"""Bot snapshots imported directly, without receipts or participant identities."""
import hashlib
import secrets

from engine.model import digest
from runner.io import ROOT
from runner.match import components
from service.store import utc_now

MAX_SOURCE_BYTES = 1024 * 1024
BASELINES = ("random", "safe", "heuristic")


def public_bot(row):
    return {k: row.get(k) for k in ("id", "name", "status", "baseline", "created", "source_sha256",
                                  "wasm_sha256", "diagnostic", "compile_log")}


def import_bot(store, executor, source, name, key=None):
    if not 1 <= len(source) <= MAX_SOURCE_BYTES:
        raise ValueError("源码须为 1 byte～1 MiB。")
    source.decode("utf-8-sig")
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise ValueError("Bot 名称须为 1～100 字符。")
    identity = "bot-" + secrets.token_hex(8)
    row = dict(id=identity, name=name, status="processing", baseline=False, created=utc_now(),
               source_sha256=hashlib.sha256(source).hexdigest(), diagnostic=None, compile_log=None)
    def resource(task, db):
        folder = store.root / "bots" / identity
        folder.mkdir(parents=True)
        path = folder / "bot.cpp"
        path.write_bytes(source)
        row.update(source=str(path))
        store.put("bot", row, create=True, db=db)
    task = executor.create("compile", dict(bot_id=identity), key,
                           request=dict(source_sha256=row["source_sha256"], name=name), resource=resource)
    return store.get("bot", task["inputs"]["bot_id"])


def baseline_records(store):
    rows = []
    version = components()
    for name in BASELINES:
        source = ROOT / f"bots/baselines/{name}.cpp"
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        identity = f"baseline-{name}-" + digest(dict(source=sha, components=version))[:16]
        try:
            row = store.get("bot", identity)
        except KeyError:
            row = dict(id=identity, name=name.title(), status="processing", baseline=True,
                       source=str(source), source_sha256=sha, created=utc_now(), diagnostic=None, compile_log=None)
        if row["status"] != "ready":
            rows.append(row)
    return rows


def prepare_baselines(store, executor):
    rows = baseline_records(store)
    if not rows:
        return
    def resource(task, db):
        for row in rows:
            source = ROOT / f"bots/baselines/{row['name'].lower()}.cpp"
            folder = store.root / "bots" / row["id"]
            folder.mkdir(parents=True, exist_ok=True)
            snapshot = folder / "bot.cpp"
            snapshot.write_bytes(source.read_bytes())
            (folder / "planner.hpp").write_bytes((ROOT / "bots/baselines/planner.hpp").read_bytes())
            row["source"] = str(snapshot)
            row.update(status="processing", diagnostic=None)
            store.put("bot", row, db=db)
    return executor.create("baselines", dict(bot_ids=[r["id"] for r in rows]), resource=resource)
