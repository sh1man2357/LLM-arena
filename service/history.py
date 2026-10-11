"""Reversible record management; frozen inputs and recording files stay intact."""
import json

from service.store import utc_now

ACTIVE = ("pending", "running")


def filter_runs(rows, *, q="", status=None, trashed=False, game_id=None):
    query = q.strip().casefold()
    return [row for row in rows
            if bool(row.get("deleted_at")) == trashed
            and (not game_id or row.get("game_id", "bomberman") == game_id)
            and (not status or row["status"] == status)
            and (not query or query in " ".join([
                row["title"], row["id"], str(row.get("map_seed", "")),
                *(e.get("name", "") for e in row["entrants"])]).casefold())]


def manage_runs(store, action, ids, *, all_finished=False, q="", status=None, game_id=None):
    if all_finished and (action != "trash" or ids):
        raise ValueError("清空操作不能指定记录，且只支持移入回收站。")
    if not all_finished and not ids:
        raise ValueError("请先选择对局记录。")
    changed = []
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if all_finished:
            rows = [json.loads(r[0]) for r in db.execute("SELECT body FROM records WHERE kind='run'")]
            rows = filter_runs(rows, q=q, status=status, game_id=game_id)
        else:
            rows = [store.get("run", identity, db=db) for identity in dict.fromkeys(ids)]
        for row in rows:
            if action == "trash":
                task = store.get("task", row["task_id"], db=db)
                if row["status"] in ACTIVE or task["status"] in ACTIVE:
                    if all_finished:
                        continue
                    raise FileExistsError("对局仍在执行，请结束后再删除。")
                if row.get("deleted_at"):
                    continue
                row["deleted_at"] = utc_now()
            else:
                if not row.get("deleted_at"):
                    continue
                row.pop("deleted_at")
            store.put("run", row, db=db)
            changed.append(row["id"])
    for identity in changed:
        store.emit(identity, "run", dict(status="trashed" if action == "trash" else "restored"))
    return dict(changed=len(changed))
