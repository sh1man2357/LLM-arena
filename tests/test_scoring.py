import copy
import struct
import tempfile
from pathlib import Path
import unittest

from engine.model import Bomb, Rules, WAIT
from engine.rules import step
from replay.verify import verify_world, verify_bot
from runner.match import account, empty_stats, run_match
from runtime.protocol import encode
from runtime.wasm import Backend, InitializationError, QualificationError
from service.replays import project
from tests.test_engine import arena, act
from tests.test_runtime import module


class ScoringTests(unittest.TestCase):
    def test_survival_includes_wait_but_excludes_death_tick(self):
        w = arena([(1, 1), (7, 5)])
        act(w, WAIT, WAIT)
        self.assertEqual([p.score for p in w.players], [1, 1])
        step(w, {0: dict(fault='trap'), 1: dict(raw_action=WAIT)})
        self.assertEqual([p.score for p in w.players], [1, 2])
        self.assertEqual([p.kills for p in w.players], [0, 0])

    def test_common_hit_same_owner_deduplicated_and_self_excluded(self):
        w = arena([(1, 5), (7, 5), (4, 3)])
        w.bombs = [Bomb(0, 0, 2, 3, 0, 4), Bomb(1, 1, 6, 3, 0, 4), Bomb(2, 0, 4, 1, 0, 4)]
        calls = {p.id: dict(raw_action=WAIT) for p in w.players}
        _, events = step(w, calls)
        self.assertEqual([p.score for p in w.players], [101, 101, 0])
        self.assertEqual([p.kills for p in w.players], [1, 1, 0])
        stats = [empty_stats() for _ in w.players]
        account(stats, calls, events, 2)
        self.assertEqual([s['kills'] for s in stats], [1, 1, 0])
        self.assertEqual(stats[2]['mixed_deaths'], 1)
        w = arena([(3, 3), (5, 3)])
        w.bombs = [Bomb(0, 0, 2, 3, 0, 4), Bomb(1, 1, 6, 3, 0, 4)]
        act(w, WAIT, WAIT)
        self.assertEqual([p.score for p in w.players], [100, 100])
        self.assertEqual(w.standings()[0], [[0, 1]])

    def test_self_kill_and_chain_keep_actual_bomb_owner(self):
        w = arena([(3, 3), (7, 5)])
        w.bombs = [Bomb(0, 0, 3, 3, 0, 3)]
        act(w, WAIT, WAIT)
        self.assertEqual([p.score for p in w.players], [0, 1])
        w = arena([(1, 1), (7, 5), (5, 3)])
        w.bombs = [Bomb(0, 0, 1, 3, 0, 6), Bomb(1, 1, 3, 3, 9, 3)]
        act(w, WAIT, WAIT, WAIT)
        self.assertEqual([p.kills for p in w.players], [0, 1, 0])
        self.assertEqual([p.score for p in w.players], [0, 101, 0])

    def test_dead_owner_gets_delayed_credit_and_can_outscore_survivor(self):
        w = arena([(1, 1), (7, 5), (7, 1)])
        w.bombs = [Bomb(0, 0, 4, 5, 1, 3)]
        step(w, {0: dict(fault='trap'), 1: dict(raw_action=WAIT), 2: dict(raw_action=WAIT)})
        act(w, WAIT, WAIT, WAIT)
        self.assertEqual([p.score for p in w.players], [100, 1, 2])
        self.assertEqual(w.standings()[0], [[0], [2], [1]])
        self.assertEqual(w.standings()[1][0]['kill_score'], 100)

    def test_equal_points_tie_regardless_of_survival_or_death_time(self):
        w = arena([(1, 1), (7, 5), (7, 1)])
        w.players[0].alive, w.players[0].death_tick = False, 0
        w.players[1].alive, w.players[1].death_tick = False, 1
        for p in w.players: p.score = 100
        self.assertEqual(w.standings()[0], [[0, 1, 2]])
        self.assertEqual([p['placement_score'] for p in w.standings()[1]], [.5]*3)

    def test_protocol_v2_exposes_points_and_preserves_v1_layout(self):
        w = arena([(1, 1), (7, 5)])
        w.players[1].score, w.players[1].kills = 123, 1
        data = encode(w, 1)
        self.assertEqual(len(data), 60 + 63 + 48)
        self.assertEqual(struct.unpack('<3I', data[48:60]), (2, 1, 100))
        self.assertEqual(struct.unpack('<6I', data[147:171]), (1, 7, 5, 1, 123, 1))
        self.assertEqual(len(encode(w, 1, 1)), 48 + 63 + 32)

    def test_old_wasm_uses_v1_and_both_rules_replay_without_migration(self):
        # A frozen v1 binary rejects any v2 observation. It must still compete.
        data = module('local.get 0 i32.load i32.const 1 i32.ne if unreachable end i32.const 0')
        with tempfile.TemporaryDirectory() as folder, Backend() as backend:
            path = Path(folder) / 'old.wasm'; path.write_bytes(data)
            entrants = [dict(id=str(i), wasm=str(path)) for i in range(2)]
            for version in (1, 2):
                rules = Rules(scoring_version=version)
                result, records = run_match(backend, entrants, 1, [1, 2], rules=rules)
                self.assertTrue(result['valid'])
                self.assertTrue(all(not c['fault'] for r in records for c in r.get('calls', [])))
                verify_world(records); verify_bot(backend, records, [path, path])
                self.assertTrue(project(records)['verified'])
                self.assertEqual('score' in records[-2]['state']['players'][0], version == 2)
                self.assertEqual('scoring_version' in records[0]['rules'], version == 2)
            changed = copy.deepcopy(records)
            changed[0]['initial_state']['players'][0]['score'] = 1
            with self.assertRaisesRegex(ValueError, 'Initial scores'): verify_world(changed)

    def test_capability_export_validation_and_budget(self):
        with tempfile.TemporaryDirectory() as folder, Backend() as backend:
            path = Path(folder) / 'bot.wasm'
            path.write_bytes(module(extra='(func (export "arena_protocol_version") (param i32) (result i32) i32.const 2)'))
            with self.assertRaises(QualificationError): backend.load(path)
            for body in ('i32.const 3', '(loop $l br $l) i32.const 2', 'unreachable'):
                path.write_bytes(module(extra=f'(func (export "arena_protocol_version") (result i32) {body})'))
                with self.assertRaises(InitializationError): backend.instance(backend.load(path), 1, init_fuel=100)
