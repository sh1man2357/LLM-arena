import copy
from pathlib import Path
import tempfile
import unittest
import time
import json
import zipfile
from engine.model import digest, Rules
from engine.maps import generate
from runtime.wasm import Backend, QualificationError
from runner.io import ROOT, read_json, write_json, write_lines, sha_file
from runner.match import run_match, qualify
from runner.tournament import run_tournament, schedule, validate_cases
from runner.report import aggregate, generate_report, interval
from replay.verify import verify_world, verify_bot, verify_scheduled
from tests.test_runtime import module


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = []
        for name, data in (("a", module()), ("b", module())):
            path = self.root / f"{name}.wasm"; path.write_bytes(data); self.paths.append(str(path))
        self.entrants = [dict(id=name, wasm=path) for name, path in zip(("a", "b"), self.paths)]
        self.cases = [dict(map_seed=i, bot_seeds=["fedcba9876543210", "0123456789abcdef"]) for i in (1, 2)]

    def tearDown(self):
        self.temp.cleanup()

    def test_match_replay_rerun_and_tamper(self):
        with Backend() as backend:
            result, records = run_match(backend, self.entrants, 1, [1, 2])
            self.assertEqual(result["reason"], "tick_limit")
            self.assertEqual(result["ticks"], 500)
            verify_world(records); verify_bot(backend, records, self.paths)
            for position, key, value in ((1, "after_hash", "wrong"), (-1, "ticks", 499),
                                          (0, "map_seed", 2)):
                changed = copy.deepcopy(records); changed[position][key] = value
                with self.assertRaises(ValueError):
                    verify_world(changed)

    def test_record_sink_is_a_snapshot_and_failure_is_not_a_win(self):
        with Backend() as backend:
            expected, raw = run_match(backend, self.entrants, 1, [1, 2], rules=Rules(max_ticks=8))
            seen = []
            def observer(record):
                seen.append(copy.deepcopy(record))
                record.clear()  # A consumer cannot mutate the runner's stored evidence.
            actual, records = run_match(backend, self.entrants, 1, [1, 2], rules=Rules(max_ticks=8), record_sink=observer)
            self.assertEqual(actual, expected)
            self.assertEqual(records, raw)
            self.assertEqual(seen, raw)
            def broken(record):
                if record['type'] == 'tick':
                    raise OSError('durable stream unavailable')
            failed, _ = run_match(backend, self.entrants, 1, [1, 2], record_sink=broken)
            self.assertFalse(failed['valid'])
            self.assertEqual(failed['players'], [])
            self.assertEqual(failed['reason'], 'infrastructure_failure')

    def test_new_observed_runner_matches_frozen_v01_reference(self):
        archive_path = ROOT / 'artifacts/acceptance/v0.1-release/evidence.zip'
        with zipfile.ZipFile(archive_path) as archive, Backend() as backend:
            plan = json.loads(archive.read('schedule.json'))
            for name in ('heuristic', 'safe', 'random'):
                (self.root / f'{name}.wasm').write_bytes(archive.read(f'build/{name}.wasm'))
            samples = [p for p in plan if p['case_index'] == 0]
            self.assertEqual(len(samples), 6)
            for item in samples:
                expected = [json.loads(line) for line in archive.read(f"replays/{item['match_id']}.jsonl").decode().splitlines()]
                observed = []
                def sink(record):
                    observed.append(record)
                    if record['type'] == 'tick':
                        time.sleep(.0001)  # Host presentation delay is outside Bot fuel / world hashes.
                _, records = run_match(backend, [dict(id=eid, wasm=str(self.root / f'{eid}.wasm')) for eid in item['entrants']],
                                       item['map_seed'], [int(s,16) for s in item['bot_seeds']], item['match_id'],
                                       version=expected[0]['components'], record_sink=sink)
                self.assertEqual(records, expected)
                self.assertEqual(observed, expected)

    def test_initialization_all_fail_and_one_fail(self):
        failed = self.root / "fail.wasm"; failed.write_bytes(module(init="unreachable"))
        with Backend() as backend:
            for paths, expected in (([str(failed), str(failed)], [.5, .5]),
                                    ([str(failed), self.paths[1]], [0, 1])):
                entrants = [dict(id=str(i), wasm=p) for i, p in enumerate(paths)]
                r, records = run_match(backend, entrants, 1, [1, 2])
                self.assertEqual(r["reason"], "initialization_end")
                self.assertEqual(r["ticks"], 0)
                self.assertEqual([p["placement_score"] for p in r["players"]], expected)
                verify_world(records)

    def test_runtime_elimination_recorded_not_selfkill(self):
        failed = self.root / "fuel.wasm"; failed.write_bytes(module("(loop $l br $l) i32.const 0"))
        with Backend() as backend:
            r, records = run_match(backend, [dict(id="fuel", wasm=str(failed)), self.entrants[1]], 1, [1, 2])
            self.assertEqual(r["ticks"], 3)
            self.assertEqual(r["stats"][0]["fuel_exhaustions"], 3)
            self.assertEqual(r["stats"][0]["runtime_eliminations"], 1)
            self.assertEqual(r["stats"][0]["self_kills"], 0)
            verify_world(records)

    def test_qualification_refuses_smoke_fault(self):
        bad = self.root / "bad.wasm"; bad.write_bytes(module("i32.const 99"))
        with Backend() as backend:
            with self.assertRaises(ValueError): qualify(backend, bad)

    def test_schedule_seed_follows_entrant(self):
        plan = schedule(self.entrants, self.cases)
        self.assertEqual(len(plan), 4)
        self.assertEqual(plan[0]["entrants"], ["a", "b"])
        self.assertEqual(plan[1]["entrants"], ["b", "a"])
        self.assertEqual(plan[0]["bot_seeds"], list(reversed(plan[1]["bot_seeds"])))
        with self.assertRaises(ValueError): validate_cases([self.cases[0], self.cases[0]])
        ambiguous = [dict(id=name) for name in ("a", "a--b", "b--c", "c")]
        collision_plan = schedule(ambiguous, self.cases[:1])
        self.assertEqual(len({p["match_id"] for p in collision_plan}), 12)

    def test_tournament_resume_report_and_missing_duplicate(self):
        folder = self.root / "run"
        manifest, plan, results = run_tournament(self.entrants, self.cases, folder)
        hashes = {p.name: sha_file(p) for p in (folder / "replays").glob("*.jsonl")}
        again = run_tournament(self.entrants, self.cases, folder, resume=True)[2]
        self.assertEqual(results, again)
        self.assertEqual(hashes, {p.name: sha_file(p) for p in (folder / "replays").glob("*.jsonl")})
        self.assertEqual(generate_report(folder)["status"], "complete")
        self.assertEqual(aggregate(manifest, plan, results[:-1])["status"], "incomplete")
        with self.assertRaises(ValueError): aggregate(manifest, plan, results+[results[0]])
        failed = copy.deepcopy(results); failed[0]["valid"] = False
        self.assertEqual(aggregate(manifest, plan, failed)["status"], "incomplete")
        altered = copy.deepcopy(self.cases); altered[0]["bot_seeds"][0] = "0000000000000001"
        with self.assertRaises(ValueError): run_tournament(self.entrants, altered, folder, resume=True)
        # Result-file tampering is detected against the separately hashed Replay.
        results[0]["players"][0]["placement_score"] = 1
        write_lines(folder / "results.jsonl", results)
        with self.assertRaises(ValueError): generate_report(folder)

    def test_bootstrap_deterministic(self):
        self.assertEqual(interval([.5]*50), [.5, .5])
        self.assertEqual(interval([0, 1]*25), interval([0, 1]*25))
        self.assertIsNone(interval([1]*9))

    def test_failed_match_retry_preserves_evidence_and_scores_once(self):
        folder = self.root / "failed-retry"
        fail_once = True
        def observer(kind, value):
            nonlocal fail_once
            if kind == "record" and value["record"]["type"] == "tick" and fail_once:
                fail_once = False
                raise OSError("first durable write failed")
        _, plan, results = run_tournament(self.entrants, self.cases[:1], folder, observer=observer)
        self.assertFalse(results[0]["valid"])
        self.assertEqual(results[0]["players"], [])
        self.assertTrue(results[1]["valid"])
        self.assertEqual(generate_report(folder)["status"], "incomplete")
        failed_id, completed_id = [item["match_id"] for item in plan]
        failed_replay = (folder / "replays" / f"{failed_id}.jsonl").read_bytes()
        completed_hash = sha_file(folder / "replays" / f"{completed_id}.jsonl")
        unchanged = run_tournament(self.entrants, self.cases[:1], folder, resume=True)[2]
        self.assertEqual(unchanged, results)
        self.assertFalse((folder / "failed_attempts").exists())
        retried = run_tournament(self.entrants, self.cases[:1], folder, resume=True, retry_failures=True)[2]
        archived = folder / "failed_attempts" / failed_id
        self.assertEqual((archived / "0.replay.jsonl").read_bytes(), failed_replay)
        self.assertEqual(read_json(archived / "0.result.json"), results[0])
        self.assertEqual(sha_file(folder / "replays" / f"{completed_id}.jsonl"), completed_hash)
        self.assertEqual(len(retried), 2)
        self.assertEqual(len({result["match_id"] for result in retried}), 2)
        self.assertTrue(all(result["valid"] for result in retried))
        self.assertEqual(generate_report(folder)["status"], "complete")
        run_tournament(self.entrants, self.cases[:1], folder, resume=True, retry_failures=True)
        self.assertEqual(len(list(archived.glob("*.result.json"))), 1)

    def test_frozen_manifest_bound_to_replay(self):
        folder = self.root / "bound"
        manifest, plan, _ = run_tournament(self.entrants, self.cases[:1], folder)
        from replay.verify import read
        records = read(folder / "replays" / f"{plan[0]['match_id']}.jsonl")
        verify_scheduled(records, plan[0], manifest)
        for key, value in (("map_seed", 2), ("bot_seeds", ["0000000000000000"]*2)):
            altered = copy.deepcopy(plan[0]); altered[key] = value
            with self.assertRaises(ValueError): verify_scheduled(records, altered, manifest)
        altered = copy.deepcopy(manifest); altered["budget"]["tick_fuel"] = 10
        with self.assertRaises(ValueError): verify_scheduled(records, plan[0], altered)

    def test_text_view_includes_actions_entities_and_events(self):
        from replay.view import frames
        with Backend() as backend:
            _, records = run_match(backend, self.entrants, 1, [1, 2], rules=Rules(max_ticks=1))
        text = "\n".join(frames(records))
        for required in ("tick 0", "actions:", "calls:", "players:", "bombs:", "events:", "result:"):
            self.assertIn(required, text)

    def test_infrastructure_failure_keeps_header_without_scores(self):
        from unittest.mock import patch
        from runtime.wasm import InfrastructureError
        with Backend() as backend, patch.object(backend, "instance", side_effect=InfrastructureError("watchdog")):
            r, records = run_match(backend, self.entrants, 1, [1, 2])
            self.assertFalse(r["valid"])
            self.assertEqual(r["players"], [])
            self.assertEqual(records[0]["type"], "header")
            self.assertEqual(records[-1]["reason"], "infrastructure_failure")


if __name__ == "__main__":
    unittest.main()
