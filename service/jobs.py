"""Single compute slot. Durable handoff, no waiting queue or resume workflow."""
import json
import os
import secrets
import subprocess
import sys
import threading

from engine.model import digest
from runner.io import ROOT
from service.store import utc_now


class BusyError(Exception):
    pass


class Executor:
    def __init__(self, store):
        self.store = store
        self.shutdown = threading.Event()
        self.thread = self.process = self.workspace_lock = self.worker_tree = None
        self.process_lock = threading.Lock()

    def create(self, kind, inputs, key=None, *, request=None, resource=None):
        if kind not in ("compile", "match", "baselines"):
            raise ValueError("Unsupported core task")
        request_hash = digest(dict(kind=kind, request=request if request is not None else inputs))
        key = key or secrets.token_hex(16)
        if not 1 <= len(key) <= 128:
            raise ValueError("Idempotency key must contain 1..128 characters")
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            tasks = [json.loads(r[0]) for r in db.execute("SELECT body FROM records WHERE kind='task'")]
            for previous in tasks:
                if previous["key"] == key:
                    if previous["request_hash"] != request_hash:
                        raise FileExistsError("该请求标识已用于不同的输入。")
                    return previous
            if any(t["status"] in ("pending", "running") for t in tasks):
                raise BusyError("正在编译或运行，请完成后再试。")
            task = dict(id="task-" + secrets.token_hex(8), kind=kind, inputs=inputs, key=key,
                        request_hash=request_hash, status="pending", created=utc_now(), diagnostic=None)
            if resource:
                resource(task, db)
            self.store.put("task", task, create=True, db=db)
        self.store.emit(task["id"], "task", dict(status="pending"))
        return task

    def start(self):
        if self.thread:
            raise RuntimeError("Executor already started")
        self.lock_workspace()
        self.recover_interrupted()
        self.thread = threading.Thread(target=self.loop, name="arena-executor", daemon=True)
        self.thread.start()

    def lock_workspace(self):
        self.workspace_lock = (self.store.root / "worker.lock").open("a+b")
        try:
            self.workspace_lock.seek(0)
            if os.name == "nt":
                import msvcrt
                if not self.workspace_lock.read(1):
                    self.workspace_lock.write(b"0")
                    self.workspace_lock.flush()
                self.workspace_lock.seek(0)
                msvcrt.locking(self.workspace_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.workspace_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.workspace_lock.close()
            self.workspace_lock = None
            raise RuntimeError("Another service owns this data workspace")

    def settle(self, task):
        if task["status"] not in ("failed", "interrupted"):
            return
        inputs = task["inputs"]
        identities = [("bot", inputs["bot_id"])] if "bot_id" in inputs else []
        identities += [("bot", i) for i in inputs.get("bot_ids", [])]
        if "match_id" in inputs:
            identities.append(("run", inputs["match_id"]))
        identities += [("run", leg["match_id"]) for leg in inputs.get("legs", []) if leg["match_id"] != inputs.get("match_id")]
        for kind, identity in identities:
            row = self.store.get(kind, identity)
            if row["status"] not in ("pending", "running", "processing"):
                continue
            status = "failed" if kind == "bot" else task["status"]
            self.store.update(kind, identity, lambda r: r.update(status=status, diagnostic=task["diagnostic"]))
            self.store.emit(identity, kind, dict(status=status))

    def recover_interrupted(self):
        # Legacy job/submission/match records remain untouched.
        for task in self.store.list("task"):
            if task["status"] in ("pending", "running"):
                task.update(status="interrupted", finished=utc_now(), diagnostic="服务已退出，本次执行中断；可重新导入或重新运行。")
                self.store.put("task", task)
                self.settle(task)

    def stop(self):
        self.shutdown.set()
        self.terminate_worker()
        if self.thread:
            self.thread.join(timeout=10)
        self.recover_interrupted()
        if self.workspace_lock:
            self.workspace_lock.close()
            self.workspace_lock = None

    def terminate_worker(self):
        with self.process_lock:
            process = self.process
            if not process or process.poll() is not None:
                return
            if os.name == "nt":
                if self.worker_tree:
                    self.worker_tree.close()
                else:
                    process.kill()
            else:
                import signal
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def loop(self):
        while not self.shutdown.is_set():
            pending = [t for t in self.store.list("task") if t["status"] == "pending"]
            if not pending:
                self.shutdown.wait(.2)
                continue
            task = pending[0]
            task = self.store.update("task", task["id"], lambda r: r.update(status="running", started=utc_now()))
            folder = self.store.root / "tasks" / task["id"]
            folder.mkdir(parents=True, exist_ok=True)
            try:
                with (folder / "worker.log").open("w", encoding="utf-8") as log:
                    with self.process_lock:
                        self.process = subprocess.Popen(
                            [sys.executable, "-m", "service.worker", str(self.store.root), task["id"], "--supervised"],
                            cwd=ROOT, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=os.name != "nt",
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                        if os.name == "nt":
                            from service.process_tree import WindowsProcessTree
                            self.worker_tree = WindowsProcessTree(self.process)
                        if not self.shutdown.is_set():
                            self.process.stdin.write(b"owned\n")
                        self.process.stdin.close()
                    while self.process.poll() is None and not self.shutdown.is_set():
                        self.shutdown.wait(.1)
                    self.terminate_worker()
                    code = self.process.returncode
                def finish(current):
                    if current["status"] in ("pending", "running"):
                        current.update(status="interrupted" if self.shutdown.is_set() else "failed",
                                       finished=utc_now(), diagnostic=f"执行进程未完成（退出码 {code}）。")
                current = self.store.update("task", task["id"], finish)
                self.settle(current)
            except Exception as exc:
                self.terminate_worker()
                current = self.store.update("task", task["id"], lambda r: r.update(
                    status="interrupted" if self.shutdown.is_set() else "failed", finished=utc_now(),
                    diagnostic=f"{type(exc).__name__}: {exc}"))
                self.settle(current)
            finally:
                with self.process_lock:
                    if self.worker_tree:
                        self.worker_tree.close()
                    self.worker_tree = self.process = None
                self.store.emit(task["id"], "task", dict(status=self.store.get("task", task["id"])["status"]))
