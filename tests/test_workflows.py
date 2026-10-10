"""Submission fairness, durable job races, and actual compiler/live runner integration."""
from service.reference import reference_archive
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile

from fastapi.testclient import TestClient
from runner.io import ROOT, sha_file
from service.app import create_app
from service.jobs import Queue
from service.store import Store
from service.submissions import create_session, session_view, submit


class WorkflowBoundaryTests(unittest.TestCase):
    def test_exact_deadline_early_freeze_late_and_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            now = datetime.now(timezone.utc)
            start = now - timedelta(minutes=65)
            session = create_session(store, "Deadline", "test", start.isoformat(), "external_record")
            self.assertEqual(session_view(session)["status"], "missing")
            on_time = submit(store, session["id"], "final", received_at=(start+timedelta(minutes=60)).isoformat())
            self.assertFalse(on_time["late"])
            self.assertEqual(submit(store, session["id"], "final")["id"], on_time["id"])
            with self.assertRaises(FileExistsError):
                submit(store, session["id"], "changed")
            self.assertEqual(Path(on_time["source"]).read_text(), "final")
            late = create_session(store, "Late", "test", start.isoformat(), "external_record")
            self.assertTrue(submit(store, late["id"], "late", received_at=(start+timedelta(minutes=60, microseconds=1)).isoformat())["late"])
            early = create_session(store, "Early", "test")
            self.assertFalse(submit(store, early["id"], "early")["late"])

    def test_concurrent_idempotent_creation_is_one_job_and_one_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            store, request = Store(folder), dict(case_count=50, entrant_ids=["a", "b"])
            queue = Queue(store)
            def create(index):
                def parent(job, db):
                    store.put("tournament", dict(id=f"t-{index}", job_id=job["id"], status="queued"), create=True, db=db)
                return queue.create("tournament", dict(tournament_id=f"t-{index}"), "same", request=request, resource=parent)
            with ThreadPoolExecutor(max_workers=8) as pool:
                jobs = list(pool.map(create, range(8)))
            self.assertEqual(len({j["id"] for j in jobs}), 1)
            self.assertEqual(len(store.list("tournament")), 1)
            self.assertEqual(len(store.list("job")), 1)
            with self.assertRaises(FileExistsError):
                queue.create("tournament", {}, "same", request={})
            self.assertEqual(queue.request_stop(jobs[0]["id"])["status"], "stopped")
            self.assertEqual(queue.resume(jobs[0]["id"])["status"], "queued")

    def test_workspace_lock_and_interrupted_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            queue = Queue(store)
            job = queue.create("compile", {})
            store.update("job", job["id"], lambda r: r.update(status="running"))
            store.put("submission", dict(id="sub-test", status="compiling"))
            queue.start()
            try:
                self.assertEqual(store.get("job", job["id"])["status"], "interrupted")
                self.assertEqual(store.get("submission", "sub-test")["status"], "interrupted")
                with self.assertRaises(RuntimeError):
                    Queue(Store(folder)).start()
                store.update("job", job["id"], lambda r: r.update(status="stop_requested"))
                store.update("job", job["id"], lambda r: r.update(progress=17))
                self.assertEqual(store.get("job", job["id"])["status"], "stop_requested")
            finally:
                queue.stop()

    def test_session_idempotence_receipt_boundary_and_private_source(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            with TestClient(app) as client:
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                headers = {"idempotency-key": "session-create"}
                a = client.post("/api/v1/sessions", json={"name": "Test"}, headers=headers)
                b = client.post("/api/v1/sessions", json={"name": "Test"}, headers=headers)
                self.assertEqual(a.json()["id"], b.json()["id"])
                self.assertEqual(client.post("/api/v1/sessions", json={"name": "Other"}, headers=headers).status_code, 409)
                path = f"/api/v1/sessions/{a.json()['id']}/submit"
                self.assertEqual(client.post(path, json={"source": "x", "received_at": a.json()["started_at"]}).status_code, 422)
                self.assertEqual(client.post(path, json={"source": "x"*(1024*1024+1)}).status_code, 413)
                result = client.post(path, json={"source": "final"}).json()
                client.cookies.clear()
                self.assertEqual(client.get(f"/api/v1/submissions/{result['id']}/source").status_code, 403)


class RealWorkflowTests(unittest.TestCase):
    def wait(self, client, identity, statuses=("succeeded", "failed", "stopped"), timeout=60):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            row = client.get(f"/api/v1/jobs/{identity}").json()
            if row["status"] in statuses:
                return row
            time.sleep(.03)
        self.fail(f"Job timed out: {row}")

    def test_compile_live_stop_resume_and_sealed_disclosure(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder, workers=True)
            store = app.state.store
            safe = Path(folder) / "safe.wasm"
            with zipfile.ZipFile(reference_archive()) as archive:
                safe.write_bytes(archive.read("build/safe.wasm"))
            store.put("entrant", dict(id="safe", name="Safe", status="qualified", wasm=str(safe), wasm_sha256=sha_file(safe)))
            with TestClient(app) as client:
                client.post("/api/v1/admin/unlock", headers={"x-arena-local": "1"})
                session = client.post("/api/v1/sessions", json={"name": "工程 Wait", "model": "test fixture"}).json()
                source = '#include "arena.hpp"\nnamespace bot { void init(uint64_t) {} Action tick(const GameState&) { return Action::WAIT; } }\n'
                submitted = client.post(f"/api/v1/sessions/{session['id']}/submit", json={"source": source}).json()
                job = client.post(f"/api/v1/submissions/{submitted['id']}/compile", headers={"idempotency-key": "compile"}).json()
                complete = self.wait(client, job["id"])
                self.assertEqual(complete["status"], "succeeded", complete)
                submission = client.get(f"/api/v1/submissions/{submitted['id']}").json()
                self.assertEqual(submission["status"], "qualified")
                ids = ["safe", submission["entrant_id"]]
                body = dict(entrant_ids=ids, case_count=2, official=True)
                job = client.post("/api/v1/tournaments", json=body, headers={"idempotency-key": "batch"}).json()
                self.assertEqual(client.post("/api/v1/tournaments", json=body, headers={"idempotency-key": "batch"}).json()["id"], job["id"])
                identity = job["resources"]["tournament_id"]
                deadline, live = time.monotonic()+30, None
                while time.monotonic() < deadline:
                    rows = client.get("/api/v1/matches", params={"tournament_id": identity, "status": "running"}).json()["items"]
                    if rows:
                        frames = client.get(f"/api/v1/matches/{rows[0]['id']}/frames").json()
                        if frames.get("frames"):
                            live = rows[0]
                            self.assertTrue(frames["partial"])
                            break
                    time.sleep(.01)
                self.assertIsNotNone(live, "No real incremental frame was observed before completion")
                owner_cookies = dict(client.cookies)
                client.cookies.clear()
                self.assertEqual(client.get(f"/api/v1/matches/{live['id']}/frames").status_code, 403)
                self.assertEqual(client.get(f"/api/v1/tournaments/{identity}/report").status_code, 403)
                client.cookies.update(owner_cookies)
                self.assertEqual(client.post(f"/api/v1/jobs/{job['id']}/stop").status_code, 200)
                stopped = self.wait(client, job["id"])
                self.assertEqual(stopped["status"], "stopped", stopped)
                batch = client.get(f"/api/v1/tournaments/{identity}").json()
                self.assertGreater(batch["completed_matches"], 0)
                self.assertLess(batch["completed_matches"], 4)
                self.assertEqual(batch["report"]["status"], "incomplete")
                self.assertEqual(client.post(f"/api/v1/tournaments/{identity}/publish").status_code, 409)
                client.post(f"/api/v1/tournaments/{identity}/close-submissions")
                self.assertEqual(client.post(f"/api/v1/jobs/{job['id']}/resume").status_code, 200)
                complete = self.wait(client, job["id"])
                self.assertEqual(complete["status"], "succeeded", complete)
                self.assertEqual(len(complete["attempts"]), 2)
                self.assertEqual(client.post(f"/api/v1/tournaments/{identity}/publish").status_code, 200)
                client.cookies.clear()
                report = client.get(f"/api/v1/tournaments/{identity}/report").json()
                self.assertEqual(report["status"], "complete")
                matches = client.get("/api/v1/matches", params={"tournament_id": identity}).json()["items"]
                self.assertEqual(len(matches), 4)
                self.assertTrue(all(m["verified"] for m in matches))
                for match in matches:
                    exported = client.get(f"/api/v1/exports/{match['id']}").text
                    self.assertNotIn('"map_seed"', exported)
                    self.assertNotIn(str(ROOT).replace('\\', '\\\\'), exported)


if __name__ == "__main__":
    unittest.main()
