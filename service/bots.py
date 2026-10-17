"""Bot snapshots imported directly, without receipts or participant identities."""
import hashlib
import json
import secrets
from pathlib import Path

from engine.model import digest
from runner.compiler import FLAGS, compiler_path
from runner.io import ROOT, read_json, sha_file
from service.store import utc_now

MAX_SOURCE_BYTES = 1024 * 1024
BASELINES = ("baseline",)


def baseline_key(row):
    # Legacy snapshots used their display name as the built-in strategy key.
    return row.get("baseline_key") or row["name"].lower()


def public_bot(row):
    return dict(game_id=row.get("game_id", "bomberman"), **{k: row.get(k) for k in ("id", "name", "status", "baseline", "created", "source_sha256",
                                  "wasm_sha256", "diagnostic", "compile_log", "description", "deleted_at")})


def active_bot_ids(tasks):
    identities = set()
    for task in tasks:
        if task["status"] not in ("pending", "running"):
            continue
        inputs = task["inputs"]
        if inputs.get("bot_id"):
            identities.add(inputs["bot_id"])
        identities.update(inputs.get("bot_ids", []))
        identities.update(e["id"] for e in inputs.get("entrants", []) if e.get("kind") != "human")
    return identities


def edit_bot(store, identity, fields):
    fields = {k: v.strip() for k, v in fields.items()}
    if not fields or ("name" in fields and not 1 <= len(fields["name"]) <= 100):
        raise ValueError("Bot 名称须为 1～100 字符。")
    def change(row):
        if row.get("deleted_at"):
            raise KeyError(identity)
        if row["status"] == "processing":
            raise FileExistsError("Bot 正在编译，请完成后再编辑。")
        if row.get("baseline"):
            row["baseline_key"] = baseline_key(row)
        row.update(fields)
    row = store.update("bot", identity, change)
    store.emit(identity, "bot", dict(status=row["status"]))
    return row


def manage_bots(store, action, ids):
    if not ids:
        raise ValueError("请先选择 Bot。")
    changed = []
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        tasks = [json.loads(r[0]) for r in db.execute("SELECT body FROM records WHERE kind='task'")]
        active = active_bot_ids(tasks)
        for identity in dict.fromkeys(ids):
            row = store.get("bot", identity, db=db)
            if row.get("baseline"):
                raise FileExistsError("内置基准 Bot 不支持删除或恢复。")
            if action == "trash":
                if row["status"] == "processing" or identity in active:
                    raise FileExistsError("Bot 正在编译或参赛，请完成后再删除。")
                if row.get("deleted_at"):
                    continue
                row["deleted_at"] = utc_now()
            elif action == "restore":
                if not row.get("deleted_at"):
                    continue
                row.pop("deleted_at")
            else:
                raise ValueError("Unknown Bot management action")
            store.put("bot", row, db=db)
            changed.append(identity)
    for identity in changed:
        store.emit(identity, "bot", dict(status="trashed" if action == "trash" else "restored"))
    return dict(changed=len(changed))


def require_available_bots(store, identities, db):
    """Serialize starting a new match against moving its Bots to the bin."""
    for identity in set(identities):
        if store.get("bot", identity, db=db).get("deleted_at"):
            raise FileExistsError("Bot 已在回收站，请先恢复后再开始对局。")


def import_bot(store, executor, source, name, key=None, game_id="bomberman"):
    if game_id not in ("bomberman", "gomoku"):
        raise ValueError("Unknown game")
    if not 1 <= len(source) <= MAX_SOURCE_BYTES:
        raise ValueError("源码须为 1 byte～1 MiB。")
    source.decode("utf-8-sig")
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise ValueError("Bot 名称须为 1～100 字符。")
    identity = "bot-" + secrets.token_hex(8)
    row = dict(id=identity, name=name, game_id=game_id, status="processing", baseline=False, created=utc_now(),
               source_sha256=hashlib.sha256(source).hexdigest(), diagnostic=None, compile_log=None)
    def resource(task, db):
        folder = store.root / "bots" / identity
        folder.mkdir(parents=True)
        path = folder / "bot.cpp"
        path.write_bytes(source)
        row.update(source=str(path))
        store.put("bot", row, create=True, db=db)
    task = executor.create("compile", dict(bot_id=identity), key,
                           request=dict(source_sha256=row["source_sha256"], name=name, game_id=game_id), resource=resource)
    imported = store.get("bot", task["inputs"]["bot_id"])
    if imported.get("deleted_at"):
        raise FileExistsError("该请求对应的 Bot 已在回收站，请先恢复或重新导入。")
    return imported


def baseline_records(store, game_id="bomberman"):
    folder = "gomoku" if game_id == "gomoku" else "baselines"
    sdk = ROOT / "sdk/gomoku" if game_id == "gomoku" else ROOT / "sdk"
    header = "gomoku.hpp" if game_id == "gomoku" else "arena.hpp"
    rows = []
    version = dict(flags=FLAGS, compiler_sha256=sha_file(compiler_path()),
                   sdk_sha256={name: sha_file(sdk / name) for name in (header, 'wrapper.cpp')},
                   toolchain=read_json(ROOT / 'configs/toolchain.json'))
    headers = ('champion.hpp', 'patterns.hpp') if game_id == 'gomoku' else ('champion.hpp',)
    header_sha = {name: sha_file(ROOT / f'bots/{folder}/{name}') for name in headers}
    existing = store.list('bot')
    for name in BASELINES:
        source = ROOT / f"bots/{folder}/{name}.cpp"
        sha = sha_file(source)
        identity = f"baseline-{'gomoku-' if game_id == 'gomoku' else ''}{name}-" + digest(dict(source=sha, headers=header_sha, **version))[:16]
        # Reuse intact legacy snapshots whose build inputs match, regardless of their old ID.
        reusable = False
        for candidate in existing:
            if not (candidate.get('baseline') and candidate.get('game_id', 'bomberman') == game_id and baseline_key(candidate) == name
                    and candidate['status'] == 'ready' and candidate.get('source_sha256') == sha):
                continue
            try:
                wasm = Path(candidate['wasm'])
                metadata = read_json(wasm.with_suffix('.metadata.json'))
                if (all(metadata.get(k) == v for k, v in version.items())
                        and sha_file(candidate['source']) == sha
                        and all(sha_file(Path(candidate['source']).with_name(name)) == expected for name, expected in header_sha.items())
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
            row = dict(id=identity, name=name.title(), game_id=game_id, status="processing", baseline=True,
                       source=str(source), source_sha256=sha, created=utc_now(), diagnostic=None, compile_log=None)
        row["baseline_key"] = name
        rows.append(row)
    return rows


def listed_bots(rows, *, trashed=False):
    """One current reference per game; retired snapshots remain available to replays."""
    latest = {}
    for row in rows:
        if row.get('baseline') and baseline_key(row) in BASELINES:
            key = row.get('game_id', 'bomberman')
            previous = latest.get(key)
            if previous is None or (row['created'], row['id']) > (previous['created'], previous['id']):
                latest[key] = row
    return [row for row in rows if bool(row.get("deleted_at")) == trashed and (not row.get('baseline') or
            (baseline_key(row) in BASELINES and row['id'] == latest[row.get('game_id', 'bomberman')]['id']))]


def prepare_baselines(store, executor, game_id="bomberman"):
    rows = [r for game in (("bomberman", "gomoku") if game_id == "all" else (game_id,)) for r in baseline_records(store, game)]
    if not rows:
        return
    def resource(task, db):
        for row in rows:
            folder_name = "gomoku" if row.get("game_id") == "gomoku" else "baselines"
            source = ROOT / f"bots/{folder_name}/{baseline_key(row)}.cpp"
            folder = store.root / "bots" / row["id"]
            folder.mkdir(parents=True, exist_ok=True)
            snapshot = folder / "bot.cpp"
            snapshot.write_bytes(source.read_bytes())
            headers = ('champion.hpp', 'patterns.hpp') if row.get('game_id') == 'gomoku' else ('champion.hpp',)
            for name in headers:
                (folder / name).write_bytes((ROOT / f"bots/{folder_name}/{name}").read_bytes())
            row["source"] = str(snapshot)
            row.update(status="processing", diagnostic=None)
            store.put("bot", row, db=db)
    return executor.create("baselines", dict(bot_ids=[r["id"] for r in rows]), resource=resource)
