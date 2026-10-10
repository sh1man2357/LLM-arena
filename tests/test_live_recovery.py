"""Durable frame cursors, uncommitted results and attempt log boundaries."""
from service.reference import reference_archive
from pathlib import Path
import tempfile
import unittest
import zipfile
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from runner.io import ROOT
from service.app import create_app
from service.imports import import_replay
from service.jobs import Queue


class LiveRecoveryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(reference_archive()) as archive:
            cls.chain = archive.read("examples/chain/replay.jsonl")

    def test_cursor_watermark_and_attempt_change_return_full_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root)
            row = import_replay(app.state.store, self.chain, attempt_id="old-attempt")
            with TestClient(app) as client:
                path = f"/api/v1/matches/{row['id']}/frames"
                delta = client.get(path, params=dict(after_seq=12, attempt_id="old-attempt")).json()
                self.assertEqual([f["seq"] for f in delta["frames"]], list(range(13, 20)))
                self.assertEqual(delta["last_seq"], 19)
                self.assertFalse(delta["resync_required"])
                for params in (dict(after_seq=19, attempt_id="other-attempt"), dict(after_seq=100)):
                    full = client.get(path, params=params).json()
                    self.assertTrue(full["resync_required"])
                    self.assertEqual([f["seq"] for f in full["frames"]], list(range(20)))
                terminal = client.get(path, params=dict(after_seq=19, attempt_id="old-attempt")).json()
                self.assertEqual(terminal["frames"], [])
                self.assertTrue(terminal["result"]["valid"])

    def test_result_in_live_stream_is_not_a_committed_winner(self):
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root)
            row = import_replay(app.state.store, self.chain)
            row["live_path"] = row.pop("replay")
            row.pop("projection")
            row.update(status="failed", result=None, verified=False)
            app.state.store.put("match", row)
            with TestClient(app) as client:
                trace = client.get(f"/api/v1/matches/{row['id']}/frames").json()
                self.assertEqual(trace["last_seq"], 19)
                self.assertTrue(trace["partial"])
                self.assertFalse(trace["verified"])
                self.assertIsNone(trace["result"])

    def test_restart_closes_old_attempt_and_log_queries_stay_within_job(self):
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root)
            store = app.state.store
            job = Queue(store).create("import", {})
            job.update(status="running", attempt_id="a"*16, attempts=[dict(id="a"*16, started="original")])
            store.put("job", job)
            folder = Path(root) / "jobs" / job["id"]
            folder.mkdir(parents=True)
            (folder / ("a"*16 + ".log")).write_text("original diagnostic", encoding="utf-8")
            Queue(store).recover_interrupted()
            old = store.get("job", job["id"])
            self.assertEqual(old["attempts"][0]["status"], "interrupted")
            self.assertTrue(old["attempts"][0]["finished"])
            with TestClient(app) as client:
                path = f"/api/v1/jobs/{job['id']}/log"
                self.assertEqual(client.get(path).status_code, 403)
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                self.assertEqual(client.get(path, params=dict(attempt_id="a"*16)).text, "original diagnostic")
                self.assertEqual(client.get(path, params=dict(attempt_id="../owner.token")).status_code, 404)

    def test_terminal_attempt_is_committed_before_resume_can_change_job_status(self):
        from service.worker import update_job
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root)
            store, queue = app.state.store, Queue(app.state.store)
            row = queue.create("import", {})
            row.update(status="running", attempt_id="a"*16, attempts=[dict(id="a"*16, started="first", status="running")])
            store.put("job", row)
            ended = update_job(store, row["id"], status="stopped")
            self.assertEqual(ended["attempts"][0]["status"], "stopped")
            self.assertTrue(ended["attempts"][0]["finished"])
            queued = queue.resume(row["id"])
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(queued["attempts"], ended["attempts"])

    def test_worker_launch_failure_finishes_attempt_before_manual_retry(self):
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root)
            store, queue = app.state.store, Queue(app.state.store)
            row = queue.create("import", {})
            with patch("service.jobs.subprocess.Popen", side_effect=OSError("launch unavailable")):
                queue.start()
                try:
                    deadline = time.monotonic() + 5
                    while store.get("job", row["id"])["status"] != "failed" and time.monotonic() < deadline:
                        time.sleep(.02)
                    failed = store.get("job", row["id"])
                    self.assertEqual(failed["status"], "failed")
                    self.assertEqual(failed["attempts"][0]["status"], "failed")
                    self.assertTrue(failed["attempts"][0]["finished"])
                    self.assertIn("launch unavailable", failed["diagnostic"])
                finally:
                    queue.stop()
            resumed = queue.resume(row["id"])
            self.assertEqual(resumed["attempts"], failed["attempts"])

    def test_resume_registers_complete_cache_after_crash_before_index_commit(self):
        from runner.io import sha_file
        from runner.tournament import run_tournament
        from service.worker import run_batch
        from tests.test_runtime import module
        with tempfile.TemporaryDirectory() as root:
            app = create_app(root)
            store = app.state.store
            entrants = []
            for name in ("a", "b"):
                path = Path(root) / f"{name}.wasm"
                path.write_bytes(module())
                entrant = dict(id=name, name=name, wasm=str(path), wasm_sha256=sha_file(path), status="qualified")
                store.put("entrant", entrant)
                entrants.append(entrant)
            cases = [dict(map_seed=1, bot_seeds=["0000000000000001", "0000000000000002"])]
            tid = "t-cache"
            folder = Path(root) / "tournaments" / tid
            _, plan, _ = run_tournament(entrants, cases, folder)
            hashes = {path.name: sha_file(path) for path in (folder / "replays").glob("*.jsonl")}
            store.put("tournament", dict(id=tid, status="interrupted", expected_matches=2, disclosure="disclosed"))
            identity = tid + "-" + plan[0]["match_id"]
            store.put("match", dict(id=identity, title="cached before index", status="interrupted",
                                     verified=False, attempt_id="previous", tournament_id=tid))
            job = Queue(store).create("tournament", dict(tournament_id=tid, entrants=entrants, cases=cases))
            job.update(status="running", attempt_id="current", attempts=[dict(id="current", status="running")])
            store.put("job", job)
            run_batch(store, job)
            restored = store.get("match", identity)
            self.assertEqual(restored["status"], "completed")
            self.assertTrue(restored["verified"])
            self.assertEqual(restored["attempt_id"], "previous")
            self.assertEqual(restored["title"], "cached before index")
            self.assertEqual(hashes, {path.name: sha_file(path) for path in (folder / "replays").glob("*.jsonl")})
            self.assertEqual(len(store.list("match")), 2)
            self.assertEqual(store.get("tournament", tid)["report"]["valid_matches"], 2)


if __name__ == "__main__":
    unittest.main()
