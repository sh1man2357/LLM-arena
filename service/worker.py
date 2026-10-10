"""Owned compiler/single-run subprocess. Frames are the recording and live feed."""
import os
import sys
import time

from engine.model import canonical
from runner.compiler import compile_bot
from runner.io import read_json, sha_file
from runner.match import components, qualify, run_match
from service.replays import decode, project
from service.store import Store, utc_now
from runtime.wasm import Backend


def compile_snapshot(store, identity):
    bot = store.get("bot", identity)
    wasm = store.root / "bots" / identity / "bot.wasm"
    try:
        if sha_file(bot["source"]) != bot["source_sha256"]:
            raise ValueError("导入的源码快照已改变，请重新导入。")
        compile_bot(bot["source"], wasm)
        with Backend() as backend:
            qualify(backend, wasm)
        bot.update(status="ready", wasm=str(wasm), wasm_sha256=sha_file(wasm), diagnostic=None)
    except Exception as exc:
        bot.update(status="failed", diagnostic=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        log = wasm.with_suffix(".compile.json")
        if log.is_file():
            bot["compile_log"] = read_json(log)
        store.put("bot", bot)
        store.emit(identity, "bot", dict(status=bot["status"]))


class LiveSink:
    def __init__(self, store, identity):
        self.store, self.identity = store, identity
        self.folder = store.root / "runs" / identity
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "frames.jsonl"
        self.stream = self.path.open("w", encoding="utf-8", newline="\n")
        store.update("run", identity, lambda r: r.update(status="running", live_path=str(self.path)))
        store.emit(identity, "run", dict(status="running"))
        self.last_notice = 0

    def __call__(self, record):
        self.stream.write(canonical(record) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        ticks = record["state"]["tick"] if record["type"] == "tick" else None
        if time.monotonic() - self.last_notice > .15 or record["type"] in ("header", "result"):
            if ticks is not None:
                self.store.update("run", self.identity, lambda r: r.update(ticks=ticks))
            self.store.emit(self.identity, "frame", dict(seq=record.get("tick", -1) + 1, type=record["type"]))
            self.last_notice = time.monotonic()
        if record["type"] == "tick":
            time.sleep(.05)

    def close(self):
        self.stream.close()


def run_single(store, task):
    inputs = task["inputs"]
    for bot in inputs["entrants"]:
        if sha_file(bot["wasm"]) != bot["wasm_sha256"]:
            raise ValueError("Bot 编译产物已改变，请重新导入。")
    sink = LiveSink(store, inputs["match_id"])
    try:
        with Backend() as backend:
            result, _ = run_match(backend, inputs["entrants"], inputs["map_seed"],
                                  [int(s, 16) for s in inputs["bot_seeds"]], inputs["match_id"], record_sink=sink)
        sink.close()
        projection = project(decode(sink.path.read_bytes()), partial=not result["valid"])
        if projection["result"] is None:
            raise ValueError("运行未写入完整终局。")
        store.update("run", sink.identity, lambda r: r.update(
            status="completed" if result["valid"] else "failed", result=projection["result"],
            ticks=result["ticks"], verified=projection["verified"], finished=utc_now(),
            source_sha256=sha_file(sink.path), diagnostic=result.get("diagnostic")))
        if not result["valid"]:
            raise ValueError(result.get("diagnostic") or "运行失败。")
    finally:
        if not sink.stream.closed:
            sink.close()
        store.emit(sink.identity, "run", dict(status=store.get("run", sink.identity)["status"]))


def main(data_root, task_id):
    store = Store(data_root)
    task = store.get("task", task_id)
    if task["status"] not in ("pending", "running"):
        raise ValueError("Task is already terminal")
    store.update("task", task_id, lambda r: r.update(status="running"))
    try:
        if task["kind"] == "compile":
            compile_snapshot(store, task["inputs"]["bot_id"])
        elif task["kind"] == "baselines":
            errors = []
            for identity in task["inputs"]["bot_ids"]:
                try:
                    compile_snapshot(store, identity)
                except Exception as exc:
                    errors.append(str(exc))
            if errors:
                raise ValueError("; ".join(errors))
        elif task["kind"] == "match":
            if task["inputs"]["components"] != components():
                raise ValueError("运行输入的规则 / 工具版本已改变，请建立新运行。")
            run_single(store, task)
        else:
            raise ValueError("Unknown core task")
        store.update("task", task_id, lambda r: r.update(status="succeeded", finished=utc_now()))
    except Exception as exc:
        failed = store.update("task", task_id, lambda r: r.update(
            status="failed", finished=utc_now(), diagnostic=f"{type(exc).__name__}: {exc}"))
        from service.jobs import Executor
        Executor(store).settle(failed)
        raise


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "--supervised" and sys.stdin.readline().strip() != "owned":
        raise SystemExit("Owner vanished before releasing the worker")
    main(sys.argv[1], sys.argv[2])
