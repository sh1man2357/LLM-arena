from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import time
import unittest

from fastapi.testclient import TestClient
from gomoku.replay import project, verify_world
from replay.verify import verify_bot
from runner.io import sha_file
from service.app import create_app
from service.replays import decode
from service.worker import main as execute
from tests.test_runtime import module

HEADERS = {"X-Arena-Local": "1"}


class HumanGomokuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root)
        self.store = self.app.state.store
        self.client = TestClient(self.app)
        # Pick the first empty cell from the real binary observation.
        path = self.root / "bot.wasm"
        path.write_bytes(module('''(local $i i32)
            (block $done (loop $scan
              local.get $i i32.const 48 i32.add i32.load8_u i32.eqz br_if $done
              local.get $i i32.const 1 i32.add local.tee $i i32.const 225 i32.lt_u br_if $scan))
            local.get $i'''))
        self.store.put("bot", dict(id="bot", name="Test Bot", game_id="gomoku", status="ready", baseline=False,
                                   wasm=str(path), wasm_sha256=sha_file(path), created="2026-10-17"))
        self.workers = []
        self.errors = []

    def tearDown(self):
        for row in self.store.list("run"):
            if row["status"] in ("pending", "running"):
                self.store.update("run", row["id"], lambda r: r.update(status="interrupted"))
        for thread in self.workers:
            thread.join(5)
        self.client.close()
        self.temp.cleanup()

    def create(self, slot=0, key="human"):
        response = self.client.post("/api/v1/human-matches", headers={**HEADERS, "Idempotency-Key": key},
                                    json=dict(bot_id="bot", human_slot=slot))
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def start_worker(self, run):
        task_id = self.store.get("run", run["id"])["task_id"]
        def work():
            try:
                execute(self.root, task_id)
            except Exception as exc:
                self.errors.append(exc)
        thread = threading.Thread(target=work, daemon=True)
        self.workers.append(thread)
        thread.start()

    def wait(self, run, predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = self.store.get("run", run["id"])
            if predicate(row):
                return row
            if self.errors:
                self.fail(str(self.errors))
            time.sleep(.02)
        self.fail(f"Timed out waiting for run: {row}")

    def move(self, run, tick, action):
        return self.client.post(f"/api/v1/matches/{run['id']}/actions", headers=HEADERS, json=dict(tick=tick, action=action))

    def test_black_can_win_with_verified_recording_without_rating(self):
        run = self.create()
        self.assertEqual(self.create()["id"], run["id"])
        self.assertEqual(len(self.store.list("run")), 1)
        self.assertEqual(self.move(run, 0, 210).status_code, 409)
        self.start_worker(run)
        for step in range(5):
            self.wait(run, lambda r: r.get("waiting_tick") == step*2)
            self.assertEqual(self.move(run, step*2, 210+step).status_code, 200)
        done = self.wait(run, lambda r: r["status"] == "completed")
        self.assertTrue(done["verified"])
        self.assertEqual((done["result"]["reason"], done["result"]["winner"]), ("five_in_row", 0))
        records = decode(Path(done["live_path"]).read_bytes())
        self.assertEqual(verify_world(records)["ticks"], 9)
        self.assertEqual(records[0]["entrants"][0]["kind"], "human")
        with self.assertRaisesRegex(ValueError, "world verification only"):
            verify_bot(None, records, [])
        ui = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
        self.assertTrue(ui["verified"])
        self.assertEqual(len(ui["frames"]), 10)
        self.assertEqual(self.client.get("/api/v1/leaderboard?game_id=gomoku").json()["valid_matches"], 0)
        self.assertEqual(self.move(run, 10, 215).status_code, 409)
        for thread in self.workers:
            thread.join(5)
        again = self.client.post(f"/api/v1/matches/{run['id']}/rerun", headers=HEADERS)
        self.assertEqual(again.status_code, 202)
        self.assertEqual((again.json()["mode"], again.json()["human_slot"]), ("human", 0))
        self.assertNotEqual(again.json()["id"], run["id"])

    def test_white_resign_duplicate_stale_and_occupied_moves(self):
        run = self.create(1)
        self.start_worker(run)
        self.wait(run, lambda r: r.get("waiting_tick") == 1)
        self.assertEqual(self.move(run, 0, 210).status_code, 409)
        self.assertEqual(self.move(run, 1, 0).status_code, 422)
        for tick, action in ((True, 1), (1, 226), (1, -1), (1, 1.5)):
            self.assertEqual(self.move(run, tick, action).status_code, 422)
        self.assertEqual(self.move(run, 1, 210).status_code, 200)
        self.assertEqual(self.move(run, 1, 210).status_code, 200)
        self.assertEqual(self.move(run, 1, 211).status_code, 409)
        # A new client can read the same board and continue after a refresh.
        self.wait(run, lambda r: r.get("waiting_tick") == 3)
        with TestClient(self.app) as other:
            resumed = other.get(f"/api/v1/matches/{run['id']}").json()
            self.assertEqual(resumed["waiting_tick"], 3)
        self.assertEqual(self.move(run, 3, 225).status_code, 200)
        done = self.wait(run, lambda r: r["status"] == "completed")
        self.assertEqual((done["result"]["reason"], done["result"]["winner"]), ("resignation", 0))
        records = decode(Path(done["live_path"]).read_bytes())
        tampered = deepcopy(records)
        tampered[2]["calls"][0]["fuel_used"] = 1
        with self.assertRaisesRegex(ValueError, "Invalid human action"):
            project(tampered)
        tampered = deepcopy(records)
        tampered[0]["entrants"][0]["kind"] = "human"
        with self.assertRaisesRegex(ValueError, "Invalid entrant"):
            project(tampered)

    def test_validation_busy_boundary_and_restart_recovery(self):
        self.store.update("bot", "bot", lambda r: r.update(game_id="bomberman"))
        response = self.client.post("/api/v1/human-matches", headers=HEADERS, json=dict(bot_id="bot"))
        self.assertEqual(response.status_code, 422)
        self.store.update("bot", "bot", lambda r: r.update(game_id="gomoku"))
        for slot in (True, 2, -1):
            response = self.client.post("/api/v1/human-matches", headers=HEADERS, json=dict(bot_id="bot", human_slot=slot))
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post("/api/v1/human-matches", json=dict(bot_id="bot")).status_code, 403)
        run = self.create()
        self.assertEqual(self.client.post("/api/v1/human-matches", headers=HEADERS, json=dict(bot_id="bot")).status_code, 409)
        changed = self.client.post("/api/v1/human-matches", headers={**HEADERS, "Idempotency-Key": "human"},
                                   json=dict(bot_id="bot", human_slot=1))
        self.assertEqual(changed.status_code, 409)
        self.app.state.executor.recover_interrupted()
        self.assertEqual(self.store.get("run", run["id"])["status"], "interrupted")
        self.assertEqual(self.move(run, 0, 112).status_code, 409)
        self.assertFalse(self.client.get("/api/v1/status").json()["busy"])
