"""One local worker process at a time, durable queue, immutable input snapshots."""
import json
import os
import secrets
import subprocess
import sys
import threading

from engine.model import digest
from runner.io import ROOT
from service.store import utc_now


class Queue:
    def __init__(self, store):
        self.store = store
        self.shutdown = threading.Event()
        self.thread = None
        self.process = None
        self.workspace_lock = None
        self.process_lock = threading.Lock()

    def create(self, kind, inputs, key=None, *, request=None, resource=None):
        request_hash = digest(dict(kind=kind, request=request)) if request is not None else digest(dict(kind=kind, inputs=inputs))
        key = key or secrets.token_hex(16)
        if len(key) > 128:
            raise ValueError("Idempotency key exceeds 128 characters")
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT body FROM records WHERE kind='job'").fetchall()
            for row in rows:
                previous = json.loads(row[0])
                if previous["key"] == key:
                    if previous["request_hash"] != request_hash:
                        raise FileExistsError("Idempotency key already has different inputs")
                    return previous
            value = dict(id="j-" + secrets.token_hex(8), kind=kind, inputs=inputs, key=key,
                         request_hash=request_hash, status="queued", progress=0, total=1, created=utc_now(),
                         attempts=[], diagnostic=None)
            self.store.put("job", value, create=True, db=db)
            if resource:
                resource(value, db)
        self.store.emit(value["id"], "job", dict(status="queued"))
        return value

    def start(self):
        if self.thread:
            raise RuntimeError("Queue already started")
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
        for job in self.store.list("job"):
            if job["status"] in ("running", "stop_requested"):
                job.update(status="interrupted", diagnostic="Local service restarted; inspect evidence before resuming.")
                self.store.put("job", job)
        for kind in ("match", "tournament", "submission"):
            for row in self.store.list(kind):
                if row["status"] in ("running", "compiling"):
                    row.update(status="interrupted")
                    self.store.put(kind, row)
        self.thread = threading.Thread(target=self.loop, name="arena-job-queue", daemon=True)
        self.thread.start()

    def stop(self):
        self.shutdown.set()
        self.terminate_worker(self.process)
        if self.thread:
            self.thread.join(timeout=10)
        if self.workspace_lock:
            self.workspace_lock.close()
            self.workspace_lock = None

    def terminate_worker(self, process):
        if not process:
            return
        with self.process_lock:
            if process.poll() is not None:
                return
            if os.name == "nt":
                # This PID belongs to our Popen; kill its compiler descendants too.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=8)
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
            pending = sorted([j for j in self.store.list("job") if j["status"] == "queued"], key=lambda j: j["created"])
            if not pending:
                self.shutdown.wait(.2)
                continue
            job = pending[0]
            attempt = secrets.token_hex(8)
            claimed = False
            def claim(current):
                nonlocal claimed
                if current["status"] == "queued":
                    claimed = True
                    current.update(status="running", started=utc_now(), attempt_id=attempt)
                    current["attempts"].append(dict(id=attempt, started=current["started"]))
            job = self.store.update("job", job["id"], claim)
            if not claimed:
                continue
            folder = self.store.root / "jobs" / job["id"]
            folder.mkdir(parents=True, exist_ok=True)
            self.store.emit(job["id"], "job", dict(status="running"))
            with (folder / f"{attempt}.log").open("w", encoding="utf-8") as log:
                try:
                    self.process = subprocess.Popen([sys.executable, "-m", "service.worker", str(self.store.root), job["id"]],
                                                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                                    start_new_session=os.name != "nt",
                                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    while self.process.poll() is None and not self.shutdown.is_set():
                        self.shutdown.wait(.1)
                    if self.shutdown.is_set() and self.process.poll() is None:
                        self.terminate_worker(self.process)
                    def finish(current):
                        if current["attempt_id"] != attempt:
                            return
                        if current["status"] in ("running", "stop_requested"):
                            current.update(status="interrupted" if self.shutdown.is_set() else "failed",
                                           diagnostic=f"Worker stopped before committing completion (exit {self.process.returncode}).")
                        for item in current["attempts"]:
                            if item["id"] == attempt:
                                item.update(status=current["status"], finished=utc_now(), exit_code=self.process.returncode)
                    current = self.store.update("job", job["id"], finish)
                    self.store.emit(job["id"], "job", dict(status=current["status"]))
                except Exception as exc:
                    current = self.store.get("job", job["id"])
                    current.update(status="failed", diagnostic=f"{type(exc).__name__}: {exc}")
                    self.store.put("job", current)
                finally:
                    self.process = None

    def request_stop(self, identity):
        def change(job):
            if job["status"] == "queued":
                job["status"] = "stopped"
            elif job["status"] == "running":
                job["status"] = "stop_requested"
            else:
                raise FileExistsError("Only queued or running jobs can be stopped")
        job = self.store.update("job", identity, change)
        self.store.emit(identity, "job", dict(status=job["status"]))
        return job

    def resume(self, identity):
        def change(job):
            if job["status"] not in ("stopped", "interrupted", "failed"):
                raise FileExistsError("Only stopped, interrupted or failed jobs can be resumed")
            job.update(status="queued", diagnostic=None)
        job = self.store.update("job", identity, change)
        self.store.emit(identity, "job", dict(status="queued"))
        return job
