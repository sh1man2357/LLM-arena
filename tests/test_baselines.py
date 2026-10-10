"""Real compiled baseline decisions and the reported self-play stall."""
from pathlib import Path
import tempfile
import unittest

from engine.model import HARD_WALL, FLOOR, SOFT_WALL, UP, Player, World
from replay.verify import verify_bot, verify_world
from runner.compiler import compile_bot
from runner.io import ROOT
from runner.match import run_match
from runtime.protocol import encode
from runtime.wasm import Backend


class HeuristicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'heuristic.wasm'
        compile_bot(ROOT / 'bots/baselines/heuristic.cpp', cls.path)
        cls.backend = Backend()
        cls.module = cls.backend.load(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.backend.close()
        cls.temp.cleanup()

    def test_detour_can_start_by_moving_away_from_target(self):
        grid = [HARD_WALL] * (9 * 7)
        for x, y in [(3, 2), (3, 1), (4, 1), (5, 1), (7, 5)]:
            grid[y * 9 + x] = FLOOR
        grid[2 * 9 + 5] = SOFT_WALL
        world = World(9, 7, grid, [Player(0, 3, 2), Player(1, 7, 5)])
        for seed in (0, 1, 0xb842059f76dc5f3e):
            with self.subTest(seed=seed):
                instance = self.backend.instance(self.module, seed)
                try:
                    call = instance.call(encode(world, 0))
                    self.assertIsNone(call['fault'])
                    self.assertEqual(call['raw_action'], UP)
                finally:
                    instance.close()

    def test_unreachable_nearer_target_does_not_block_reachable_target(self):
        grid = [HARD_WALL] * (9 * 7)
        for x, y in [(3, 2), (7, 5), *[(x, 1) for x in range(1, 7)]]:
            grid[y * 9 + x] = FLOOR
        grid[4 * 9 + 3] = grid[1 * 9 + 7] = SOFT_WALL
        world = World(9, 7, grid, [Player(0, 3, 2), Player(1, 7, 5)])
        instance = self.backend.instance(self.module, 1)
        try:
            call = instance.call(encode(world, 0))
            self.assertIsNone(call['fault'])
            self.assertEqual(call['raw_action'], UP)
        finally:
            instance.close()

    def test_reported_self_play_seed_keeps_acting_and_replays(self):
        entrants = [dict(id='heuristic', wasm=str(self.path))] * 2
        result, records = run_match(self.backend, entrants, 2069542235,
                                   [0xb842059f76dc5f3e, 0xd45b1a70e962f3f4])
        self.assertTrue(result['valid'])
        self.assertNotEqual(result['reason'], 'tick_limit')
        ticks = [r for r in records if r['type'] == 'tick']
        self.assertTrue(any(t['tick'] > 26 and any(e['type'] == 'move' for e in t['events'])
                            for t in ticks))
        streak = longest = 0
        for tick in ticks:
            self.assertTrue(all(c['fault'] is None for c in tick['calls']))
            streak = streak + 1 if not tick['events'] and all(c['raw_action'] == 0 for c in tick['calls']) else 0
            longest = max(longest, streak)
        self.assertLess(longest, 10)
        verify_world(records)
        verify_bot(self.backend, records, [str(self.path)] * 2)
