import copy
from pathlib import Path
import tempfile
import unittest
from engine.model import digest, Rules
from engine.maps import generate
from runtime.wasm import Backend, QualificationError
from runner.io import ROOT, read_json, write_json, write_lines, sha_file
from runner.match import run_match, qualify
from replay.verify import verify_world, verify_bot
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

    def test_multiplayer_all_counts_replay_and_bot_rerun(self):
        with Backend() as backend:
            for count in range(3, 9):
                with self.subTest(count=count):
                    entrants = [self.entrants[i % 2] for i in range(count)]
                    paths = [e['wasm'] for e in entrants]
                    result, records = run_match(backend, entrants, 1, list(range(count)), rules=Rules(max_ticks=2))
                    self.assertTrue(result['valid'])
                    self.assertEqual(result['groups'], [list(range(count))])
                    self.assertEqual([p['placement_score'] for p in result['players']], [.5] * count)
                    self.assertEqual(len(result['stats']), count)
                    verify_world(records)
                    verify_bot(backend, records, paths)

    def test_multiplayer_initialization_and_runtime_eliminations_rank_individually(self):
        failed = self.root / 'init-failed.wasm'; failed.write_bytes(module(init='unreachable'))
        trapped = self.root / 'trapped.wasm'; trapped.write_bytes(module('unreachable'))
        fuel = self.root / 'fuel.wasm'; fuel.write_bytes(module('(loop $l br $l) i32.const 0'))
        paths = [str(failed), str(trapped), str(fuel), self.paths[0]]
        with Backend() as backend:
            result, records = run_match(backend, [dict(id=str(i), wasm=p) for i, p in enumerate(paths)], 1, [1, 2, 3, 4])
            self.assertEqual(result['reason'], 'last_survivor')
            self.assertEqual(result['groups'], [[3], [2], [1], [0]])
            self.assertEqual([p['placement_score'] for p in result['players']], [0, 1/3, 2/3, 1])
            verify_world(records); verify_bot(backend, records, paths)
            changed = copy.deepcopy(records); changed[0]['entrants'].pop()
            with self.assertRaises(ValueError): verify_world(changed)

    def test_match_rejects_mismatched_seeds_and_out_of_range_counts(self):
        with Backend() as backend:
            for count, seeds in ((1, [1]), (9, list(range(9))), (3, [1, 2])):
                with self.assertRaises(ValueError):
                    run_match(backend, [self.entrants[0]] * count, 1, seeds)

    def test_multiplayer_infrastructure_failure_projects_without_scores(self):
        from unittest.mock import patch
        from runtime.wasm import InfrastructureError
        from service.replays import project
        with Backend() as backend, patch.object(backend, 'instance', side_effect=InfrastructureError('watchdog')):
            result, records = run_match(backend, [self.entrants[0]] * 8, 1, list(range(8)))
        ui = project(records)
        self.assertFalse(result['valid'])
        self.assertFalse(ui['verified'])
        self.assertEqual(ui['result']['players'], [])
        self.assertEqual(len(ui['result']['stats']), 8)

    def test_cli_multiplayer_default_seeds_and_map_count(self):
        from runner.cli import execute, parser
        map_path = self.root / 'map.json'
        execute(parser().parse_args(['map', '1', '--players', '3', '--output', str(map_path)]))
        self.assertEqual(len(read_json(map_path)['spawns']), 3)
        folder = self.root / 'cli-match'
        args = ['match', '--map-seed', '1', '--output', str(folder)]
        for i in range(3):
            args += ['--bot', f'bot-{i}={self.paths[i % 2]}']
        result = execute(parser().parse_args(args))
        from replay.verify import read
        records = read(folder / 'replay.jsonl')
        self.assertTrue(result['valid'])
        self.assertEqual(records[0]['bot_seeds'], [f'{i:016x}' for i in (1, 2, 3)])
        verify_world(records)

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

    def test_same_bot_instances_keep_separate_memory_and_seed(self):
        path = self.root / 'self-play.wasm'
        path.write_bytes(module('''i32.const 65536 i32.const 65536 i32.load
            i32.const 1 i32.add i32.const 5 i32.rem_u i32.store
            i32.const 65536 i32.load''', 'i32.const 65536 local.get 1 i32.store'))
        entrants = [dict(id='same', wasm=str(path))] * 2
        with Backend() as backend:
            result, records = run_match(backend, entrants, 1, [0, 1 << 32], rules=Rules(max_ticks=8))
            self.assertTrue(result['valid'])
            ticks = [r for r in records if r['type'] == 'tick']
            self.assertEqual([[c['raw_action'] for c in r['calls']] for r in ticks],
                             [[(t + 1) % 5, (t + 2) % 5] for t in range(8)])
            verify_world(records)
            verify_bot(backend, records, [str(path), str(path)])

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
