from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from runner.io import sha_file
from service.app import create_app
from service.bots import prepare_baselines
from service.worker import main as execute, run_single
from tests.test_runtime import module

HEADERS = {"X-Arena-Local": "1"}


class GomokuServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root)
        self.store = self.app.state.store
        self.client = TestClient(self.app)
        for name, action in (("a", 112), ("b", 113)):
            path = self.root / f"{name}.wasm"
            path.write_bytes(module(f"i32.const {action}"))
            self.store.put("bot", dict(id=name, name=name, game_id="gomoku", status="ready", baseline=False,
                                       wasm=str(path), wasm_sha256=sha_file(path), created="2026-10-11"))

    def tearDown(self):
        self.client.close(); self.temp.cleanup()

    def start(self, **extra):
        return self.client.post("/api/v1/matches", headers={**HEADERS, "Idempotency-Key": "pair"},
                                json=dict(bot_ids=["a", "b"], game_id="gomoku", map_seed=2, **extra))

    def finish(self, run):
        task_id = self.store.get("run", run["id"])["task_id"]
        with patch("service.worker.time.sleep"):
            execute(self.root, task_id)
        return self.client.get(f"/api/v1/matches/{run['id']}").json()

    def test_pair_swap_seeds_rerun_and_color_statistics(self):
        response = self.start(); self.assertEqual(response.status_code, 202)
        run = response.json(); self.assertEqual(len(run["pair_runs"]), 2)
        task = self.store.get("task", self.store.get("run", run["id"])["task_id"])
        a, b = task["inputs"]["legs"]
        self.assertEqual(a["entrants"], list(reversed(b["entrants"])))
        self.assertEqual(a["bot_seeds"], list(reversed(b["bot_seeds"])))
        self.assertEqual(self.start().json()["id"], run["id"])
        self.assertEqual(len(self.store.list("run")), 2)
        self.assertEqual(self.client.get("/api/v1/leaderboard?game_id=gomoku").json()["valid_matches"], 0)
        done = self.finish(run)
        self.assertTrue(done["pair"]["counted"]); self.assertEqual(done["pair"]["score"], [1, 1])
        scores = self.client.get("/api/v1/leaderboard?game_id=gomoku").json()
        self.assertEqual(scores["valid_matches"], 2)
        for row in scores["items"]:
            self.assertEqual((row["matches"], row["black_matches"], row["white_matches"], row["mean_score"]), (2, 1, 1, .5))
        self.assertEqual(self.client.get("/api/v1/leaderboard").json()["items"], [])
        for identity in done["pair_runs"]:
            ui = self.client.get(f"/api/v1/matches/{identity}/frames").json()
            self.assertTrue(ui["verified"]); self.assertEqual(ui["game_id"], "gomoku")
        rerun = self.client.post(f"/api/v1/matches/{done['pair_runs'][1]}/rerun", headers=HEADERS)
        self.assertEqual(rerun.status_code, 202)
        next_task = self.store.get("task", self.store.get("run", rerun.json()["id"])["task_id"])
        for key in ("entrants", "map_seed", "bot_seeds", "opening_mode", "game_id"):
            self.assertEqual(task["inputs"][key], next_task["inputs"][key])
        self.finish(rerun.json())

    def test_incomplete_pair_and_trash_restore_do_not_count_half(self):
        run = self.start().json()
        task = self.store.get("task", self.store.get("run", run["id"])["task_id"])
        with patch("service.worker.time.sleep"):
            run_single(self.store, task, task["inputs"]["legs"][0])
        self.assertEqual(self.client.get("/api/v1/leaderboard?game_id=gomoku").json()["valid_matches"], 0)
        with patch("service.worker.time.sleep"):
            run_single(self.store, task, task["inputs"]["legs"][1])
        self.store.update("task", task["id"], lambda r: r.update(status="succeeded"))
        for action, count in (("trash", 0), ("restore", 2)):
            r = self.client.post("/api/v1/matches/manage", headers=HEADERS,
                                 json=dict(action=action, ids=[run["pair_runs"][1]]))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.client.get("/api/v1/leaderboard?game_id=gomoku").json()["valid_matches"], count)

    def test_second_leg_failure_settles_and_recovery_settles_both(self):
        run = self.start().json()
        task = self.store.get("task", self.store.get("run", run["id"])["task_id"])
        from gomoku.match import run_match as real_run
        calls = 0
        def interrupted(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("second leg storage unavailable")
            return real_run(*args, **kwargs)
        with patch("service.worker.time.sleep"), patch("gomoku.match.run_match", side_effect=interrupted):
            with self.assertRaises(OSError): execute(self.root, task["id"])
        self.assertEqual([self.store.get("run", i)["status"] for i in run["pair_runs"]], ["completed", "failed"])
        self.assertEqual(self.client.get("/api/v1/leaderboard?game_id=gomoku").json()["valid_matches"], 0)
        retry = self.client.post(f"/api/v1/matches/{run['id']}/rerun", headers=HEADERS).json()
        self.app.state.executor.recover_interrupted()
        self.assertEqual([self.store.get("run", i)["status"] for i in retry["pair_runs"]], ["interrupted"]*2)

    def test_game_validation_filtering_and_self_play(self):
        self.assertEqual(self.client.post("/api/v1/matches", headers=HEADERS, json=dict(bot_ids=["a", "b"])).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/matches", headers=HEADERS, json=dict(bot_ids=["a"]*3, game_id="gomoku")).status_code, 422)
        self.assertEqual(len(self.client.get("/api/v1/bots?game_id=gomoku").json()["items"]), 2)
        self.assertEqual(self.client.get("/api/v1/bots?game_id=bomberman").json()["items"], [])
        response = self.client.post("/api/v1/matches", headers=HEADERS, json=dict(bot_ids=["a"]*2, game_id="gomoku"))
        done = self.finish(response.json()); self.assertTrue(done["pair"]["complete"])
        self.assertEqual(len(self.client.get("/api/v1/matches?game_id=gomoku").json()["items"]), 2)
        self.assertEqual(self.client.get("/api/v1/matches?game_id=bomberman").json()["items"], [])
        self.assertEqual(self.client.get("/api/v1/leaderboard?game_id=gomoku").json()["items"][0]["matches"], 4)

    def test_gomoku_upload_and_both_game_baselines(self):
        source = b'#include "gomoku.hpp"\nnamespace bot { void init(uint64_t){} Action tick(const GameState&){return {7,7};} }'
        response = self.client.post("/api/v1/bots", headers=HEADERS, files={"file": ("bot.cpp", source)},
                                    data=dict(name="Chess", game_id="gomoku"))
        self.assertEqual(response.status_code, 202)
        execute(self.root, self.store.list("task")[0]["id"])
        self.assertEqual(self.store.get("bot", response.json()["id"])["status"], "ready")
        task = prepare_baselines(self.store, self.app.state.executor, "all")
        execute(self.root, task["id"])
        for game in ("gomoku", "bomberman"):
            rows = self.client.get(f"/api/v1/bots?game_id={game}").json()["items"]
            self.assertEqual(len([r for r in rows if r["baseline"] and r["status"] == "ready"]), 3)
