"""Real strategy regressions and resource budgets for the two zero-point references."""
from pathlib import Path
import random
import tempfile
import unittest

from engine.model import World as BombWorld, Player, Bomb, FLOOR, HARD_WALL, SOFT_WALL
from gomoku.rules import World
from gomoku.match import encode, run_match as gomoku_match
from gomoku import MOVE_FUEL
from runner.compiler import compile_bot
from runner.io import ROOT, read_json
from runner.match import run_match
from runtime.protocol import encode as bomb_encode
from runtime.wasm import Backend
from replay.verify import verify_world
from tools.build_gomoku_patterns import generate


class SingleBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.backend = Backend()
        cls.paths = {}
        for game, folder, names in [('gomoku', 'gomoku', ('baseline', 'search')),
                                    ('bomberman', 'baselines', ('baseline', 'heuristic'))]:
            for name in names:
                path = cls.root / f'{game}-{name}.wasm'
                compile_bot(ROOT / f'bots/{folder}/{name}.cpp', path, game)
                cls.paths[game, name] = path

    @classmethod
    def tearDownClass(cls):
        cls.backend.close(); cls.temp.cleanup()

    def test_pattern_table_is_reproducible(self):
        self.assertEqual((ROOT / 'bots/gomoku/patterns.hpp').read_text(encoding='utf-8'), generate())

    def test_gomoku_sparse_dense_and_immediate_tactics_within_budget(self):
        instance = self.backend.instance(self.backend.load(self.paths['gomoku', 'baseline']), 1, tick_fuel=MOVE_FUEL)
        instance.action_max = 225
        try:
            rng = random.Random(35)
            for count in (0, 3, 12, 30, 60, 120, 220):
                for trial in range(5):
                    w = World()
                    for k, i in enumerate(rng.sample(range(225), count)): w.grid[i] = 1+k%2
                    result = instance.call(encode(w, 0))
                    self.assertIsNone(result['fault'], (count, trial, result))
                    self.assertEqual(w.grid[result['raw_action']], 0)
            for color in (1, 2):
                for indices, expected in [([105,106,107,108], (104,109)), ([105,106,108,109], (107,))]:
                    w = World()
                    for i in indices: w.grid[i] = color
                    result = instance.call(encode(w, 0))
                    self.assertIsNone(result['fault']); self.assertIn(result['raw_action'], expected)
            # A crossing of two open threes creates a forced winning double four.
            w = World()
            for i in (110,111,97,127): w.grid[i] = 1
            result = instance.call(encode(w, 0))
            self.assertIsNone(result['fault']); self.assertEqual(result['raw_action'],112)
        finally: instance.close()

    def test_gomoku_outperforms_old_search_across_all_openings_and_colors(self):
        bots = [dict(id=n, wasm=str(self.paths['gomoku', n])) for n in ('baseline', 'search')]
        points = 0
        for seed in range(12):
            for swap in (False, True):
                result, records = gomoku_match(self.backend, bots[::-1] if swap else bots, seed,
                                                [2,1] if swap else [1,2], opening_mode='library')
                self.assertIn(result['reason'], ('five_in_row', 'board_full')); verify_world(records)
                self.assertTrue(all(not c['fault'] for t in records for c in t.get('calls', [])))
                points += result['players'][int(swap)]['placement_score']
        self.assertGreater(points, 12)

    def test_bomberman_large_maps_and_eight_players_within_budget(self):
        instance = self.backend.instance(self.backend.load(self.paths['bomberman', 'baseline']), 1)
        try:
            for crowded in (False, True):
                positions = [(15,15),(17,15),(15,17),(13,15),(15,13),(17,17),(13,13),(13,17)] if crowded else [(1,1),(29,29),(1,29),(29,1),(15,1),(15,29),(1,15),(29,15)]
                for walls in (False, True):
                    grid = [FLOOR]*961
                    for y in range(31):
                        for x in range(31):
                            if x in (0,30) or y in (0,30):grid[y*31+x]=HARD_WALL
                            elif walls and (x+y)%3==0 and (x,y) not in positions:grid[y*31+x]=SOFT_WALL
                    world = BombWorld(31,31,grid,[Player(i,*pos) for i,pos in enumerate(positions)])
                    for bombs in (False, True):
                        world.bombs = [Bomb(i,i,*pos,4,3) for i,pos in enumerate(positions)] if bombs else []
                        result = instance.call(bomb_encode(world,0))
                        self.assertIsNone(result['fault'], (crowded,walls,bombs,result))
        finally: instance.close()

    def test_bomberman_reference_games_and_old_opponent(self):
        bots = [dict(id=n,wasm=str(self.paths['bomberman',n])) for n in ('baseline','heuristic')]
        points = []
        cases = read_json(ROOT / 'configs/public-dev.json')
        for case in cases:
            for swap in (False,True):
                seeds = [int(s,16) for s in case['bot_seeds'][:2]]
                result,records = run_match(self.backend,bots[::-1] if swap else bots,case['map_seed'],seeds[::-1] if swap else seeds)
                verify_world(records)
                self.assertTrue(all(not c['fault'] for t in records for c in t.get('calls', [])))
                points.append(result['players'][int(swap)]['placement_score'])
        self.assertGreaterEqual(sum(points), len(points)/2)
