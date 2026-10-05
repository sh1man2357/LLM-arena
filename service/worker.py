"""Owned worker process for compiler and frozen deterministic competition jobs."""
import os
from pathlib import Path
import sys
import time

from engine.model import canonical
from runner.compiler import compile_bot
from runner.io import read_json, sha_file, write_json
from runner.match import components, qualify, run_match
from runner.report import generate_report
from runner.tournament import run_tournament
from runtime.wasm import Backend
from service.imports import import_replay, import_bundled, import_uploaded_archive
from service.store import Store, utc_now


class LiveSink:
    def __init__(self, store, identity, title, entrants, attempt, folder, tournament_id=None, case=None, disclosure="disclosed", interval_ms=0):
        self.store, self.identity, self.attempt = store, identity, attempt
        self.folder, self.title, self.tournament_id, self.case = folder, title, tournament_id, case
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "live.jsonl"
        self.stream = self.path.open("w", encoding="utf-8", newline="\n")
        self.row = dict(id=identity, title=title, entrants=[dict(id=e["id"], slot=i, wasm_sha256=sha_file(e["wasm"])) for i,e in enumerate(entrants)],
                        status="running", result=None, ticks=0, verified=False, disclosure=disclosure,
                        tournament_id=tournament_id, live_path=str(self.path), attempt_id=attempt,
                        created=utc_now(), case=case)
        self.store.put("match", self.row)
        self.last_notice = 0
        self.interval = interval_ms / 1000

    def __call__(self, record):
        self.stream.write(canonical(record) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        seq = record.get("tick", -1) + 1
        if record["type"] == "tick":
            self.row["ticks"] = record["state"]["tick"]
        if time.monotonic() - self.last_notice > .15 or record["type"] in ("header", "result"):
            self.row = self.store.update("match", self.identity, lambda r: r.update(ticks=self.row["ticks"]))
            self.store.emit(self.identity, "frame", dict(attempt_id=self.attempt, seq=seq, type=record["type"]))
            self.last_notice = time.monotonic()
        if record["type"] == "tick" and self.interval:
            time.sleep(self.interval)

    def close(self):
        self.stream.close()


def update_job(store, identity, **changes):
    job = store.update("job", identity, lambda r: r.update(changes))
    store.emit(identity, "job", dict(status=job["status"], progress=job["progress"]))
    return job


def compile_submission(store, job):
    submission = store.get("submission", job["inputs"]["submission_id"])
    if submission["late"]:
        raise ValueError("Late source is not eligible for this development session")
    if sha_file(submission["source"]) != submission["source_sha256"]:
        raise ValueError("Frozen source was modified")
    wasm = Path(submission["source"]).with_name("bot.wasm")
    submission.update(status="compiling", job_id=job["id"])
    store.put("submission", submission)
    try:
        compile_bot(submission["source"], wasm)
        with Backend() as backend:
            proof = qualify(backend, wasm)
        submission.update(status="qualified", wasm=str(wasm), wasm_sha256=sha_file(wasm), qualification=proof)
        eid = "e-" + submission["id"][4:]
        entrant = dict(id=eid, name=submission["name"], model=submission["model"], submission_id=submission["id"],
                       wasm=str(wasm), wasm_sha256=sha_file(wasm), status="qualified", baseline=False, created=utc_now())
        store.put("entrant", entrant)
        submission["entrant_id"] = eid
    except Exception as exc:
        submission.update(status="qualification_failed", diagnostic=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        log = wasm.with_suffix(".compile.json")
        if log.exists():
            submission["compile_log"] = read_json(log)
        store.put("submission", submission)


def finalize_match(store, sink, replay_path):
    sink.close()
    disclosure = store.get("tournament", sink.tournament_id)["disclosure"] if sink.tournament_id else sink.row["disclosure"]
    row = import_replay(store, Path(replay_path).read_bytes(), identity=sink.identity, title=sink.title,
                        tournament_id=sink.tournament_id, case=sink.case, disclosure=disclosure, attempt_id=sink.attempt)
    store.emit(row["id"], "match", dict(status=row["status"], attempt_id=sink.attempt))
    return row


def run_single(store, job):
    inputs = job["inputs"]
    folder = store.root / "jobs" / job["id"] / job["attempt_id"]
    entrants = inputs["entrants"]
    sink = LiveSink(store, inputs["match_id"], inputs["title"], entrants, job["attempt_id"], folder,
                    disclosure=inputs.get("disclosure", "disclosed"), interval_ms=inputs.get("tick_interval_ms", 0))
    try:
        with Backend() as backend:
            for e in entrants:
                qualify(backend, e["wasm"])
            result, _ = run_match(backend, entrants, inputs["map_seed"], [int(s,16) for s in inputs["bot_seeds"]],
                                  inputs["match_id"], replay_path=folder / "replay.jsonl", record_sink=sink)
        write_json(folder / "result.json", result)
        row = finalize_match(store, sink, folder / "replay.jsonl")
        if not result["valid"]:
            raise ValueError(result["diagnostic"])
        return dict(match_id=row["id"])
    except Exception:
        if not sink.stream.closed:
            sink.close()
        row = store.get("match", sink.identity)
        row.update(status="failed")
        store.put("match", row)
        raise


def run_batch(store, job):
    inputs, identity = job["inputs"], job["inputs"]["tournament_id"]
    folder = store.root / "tournaments" / identity
    folder.mkdir(parents=True, exist_ok=True)
    row = store.update("tournament", identity, lambda r: r.update(status="running"))
    sink = None

    def observer(kind, value):
        nonlocal sink
        item = value["item"]
        mid = identity + "-" + item["match_id"]
        if kind == "match_start":
            cached = folder / "matches" / f"{item['match_id']}.json"
            if cached.exists() and read_json(cached).get("valid"):
                sink = None
                return
            entrants = [next(e for e in inputs["entrants"] if e["id"] == eid) for eid in item["entrants"]]
            sink = LiveSink(store, mid, " × ".join(store.get("entrant", e["id"])["name"] for e in entrants), entrants,
                            job["attempt_id"], store.root / "jobs" / job["id"] / job["attempt_id"] / item["match_id"],
                            tournament_id=identity, case=item, disclosure=store.get("tournament", identity)["disclosure"])
        elif kind == "record":
            sink(value["record"])
        elif kind == "match_end":
            if sink:
                finalize_match(store, sink, value["replay"])
                sink = None
            else:
                try:
                    store.get("match", mid)
                except KeyError:
                    import_replay(store, Path(value["replay"]).read_bytes(), tournament_id=identity, identity=mid, case=item,
                                  disclosure=store.get("tournament", identity)["disclosure"])
            store.update("tournament", identity, lambda r: r.update(completed_matches=value["index"]+1))
            update_job(store, job["id"], progress=value["index"]+1, total=row["expected_matches"])

    try:
        manifest, plan, results = run_tournament(inputs["entrants"], inputs["cases"], folder,
                                                resume=(folder / "manifest.json").exists(), retry_failures=True,
                                                observer=observer, should_stop=lambda: store.get("job", job["id"])["status"] == "stop_requested")
        report = generate_report(folder)
        row = store.update("tournament", identity, lambda r: r.update(status=report["status"], report=report, manifest=manifest, directory=str(folder), completed_matches=len(results)))
        store.emit(identity, "tournament", dict(status=row["status"]))
        if store.get("job", job["id"])["status"] == "stop_requested":
            return dict(stopped=True, tournament_id=identity)
        if report["status"] != "complete":
            raise ValueError("Tournament incomplete; inspect failed attempts before resuming")
        return dict(tournament_id=identity)
    finally:
        if sink:
            sink.close()


def main(data_root, job_id):
    store = Store(data_root)
    job = store.get("job", job_id)
    try:
        if job["inputs"].get("components") and job["inputs"]["components"] != components():
            raise ValueError("Frozen competition code/configuration differs; create a new job")
        for e in job["inputs"].get("entrants", []):
            if sha_file(e["wasm"]) != e["wasm_sha256"]:
                raise ValueError("Frozen entrant WASM changed")
        if job["kind"] == "compile":
            compile_submission(store, job)
            result = dict(submission_id=job["inputs"]["submission_id"])
        elif job["kind"] == "match":
            result = run_single(store, job)
        elif job["kind"] == "tournament":
            result = run_batch(store, job)
        elif job["kind"] == "import":
            inputs = job["inputs"]
            row = (import_uploaded_archive(store, inputs["archive"], inputs["source_sha256"], inputs["title"])
                   if "archive" in inputs else import_bundled(store))
            result = dict(tournament_id=row["id"])
        elif job["kind"] == "backup":
            from service.backup import create_backup
            row = create_backup(store, current_job=job["id"])
            result = dict(backup_id=row["id"])
        else:
            raise ValueError("Unknown job type")
        progress = store.get("job", job_id)["progress"] if result.get("stopped") else store.get("job", job_id)["total"]
        update_job(store, job_id, status="stopped" if result.get("stopped") else "succeeded", result=result, progress=progress, finished=utc_now())
    except Exception as exc:
        if job["kind"] == "tournament":
            store.update("tournament", job["inputs"]["tournament_id"], lambda r: r.update(status="incomplete"))
        update_job(store, job_id, status="failed", diagnostic=f"{type(exc).__name__}: {exc}", finished=utc_now())
        raise


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
