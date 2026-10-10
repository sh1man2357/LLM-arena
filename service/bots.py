"""Bot snapshots imported directly, without receipts or participant identities."""
import hashlib
import secrets
from pathlib import Path

from engine.model import digest
from runner.compiler import FLAGS, compiler_path
from runner.io import ROOT, read_json, sha_file
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
    version = dict(flags=FLAGS, compiler_sha256=sha_file(compiler_path()),
                   sdk_sha256={name: sha_file(ROOT / 'sdk' / name) for name in ('arena.hpp', 'wrapper.cpp')},
                   toolchain=read_json(ROOT / 'configs/toolchain.json'))
    planner_sha = sha_file(ROOT / 'bots/baselines/planner.hpp')
    existing = store.list('bot')
    for name in BASELINES:
        source = ROOT / f"bots/baselines/{name}.cpp"
        sha = sha_file(source)
        identity = f"baseline-{name}-" + digest(dict(source=sha, planner=planner_sha, **version))[:16]
        # Reuse intact legacy snapshots whose build inputs match, regardless of their old ID.
        reusable = False
        for candidate in existing:
            if not (candidate.get('baseline') and candidate['name'] == name.title()
                    and candidate['status'] == 'ready' and candidate.get('source_sha256') == sha):
                continue
            try:
                wasm = Path(candidate['wasm'])
                metadata = read_json(wasm.with_suffix('.metadata.json'))
                if (all(metadata.get(k) == v for k, v in version.items())
                        and sha_file(candidate['source']) == sha
                        and sha_file(Path(candidate['source']).with_name('planner.hpp')) == planner_sha
                        and sha_file(wasm) == candidate['wasm_sha256']):
                    reusable = True
                    break
            except (OSError, ValueError, KeyError):
                continue
        if reusable:
            continue
        try:
            row = store.get("bot", identity)
        except KeyError:
            row = dict(id=identity, name=name.title(), status="processing", baseline=True,
                       source=str(source), source_sha256=sha, created=utc_now(), diagnostic=None, compile_log=None)
        if row["status"] != "ready":
            rows.append(row)
    return rows


def listed_bots(rows):
    """Offer the latest baseline version while retaining every stored snapshot."""
    latest = {}
    for row in rows:
        if row.get('baseline'):
            previous = latest.get(row['name'])
            if previous is None or (row['created'], row['id']) > (previous['created'], previous['id']):
                latest[row['name']] = row
    return [row for row in rows if not row.get('baseline') or row['id'] == latest[row['name']]['id']]


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
