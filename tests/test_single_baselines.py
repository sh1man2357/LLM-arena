"""Real strategy regressions and resource budgets for the two zero-point references."""
from pathlib import Path
import random
from copy import deepcopy
import tempfile
import unittest

from engine.model import World as BombWorld, Player, Bomb, FLOOR, HARD_WALL, SOFT_WALL
from engine.rules import explode, step as bomb_step
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

    def test_gomoku_continuous_four_and_enemy_counterwin(self):
        instance = self.backend.instance(self.backend.load(self.paths['gomoku', 'baseline']), 1, tick_fuel=MOVE_FUEL)
        instance.action_max = 225
        try:
            for color in (1, 2):
                for rotation in range(4):
                    def index(x, y):
                        for _ in range(rotation): x, y = 14-y, x
                        return y*15+x
                    w = World()
                    for x, y in ((4,7),(5,7),(6,7),(7,5),(7,8)): w.grid[index(x,y)] = color
                    w.grid[index(3,7)] = 3-color
                    if color == 2: w.moves = [dict(x=index(3,7)%15,y=index(3,7)//15,color=1)]
                    # Force a horizontal block, then turn into an open vertical four.
                    first = instance.call(encode(w,color-1))
                    self.assertIsNone(first['fault']); self.assertEqual(first['raw_action'],index(7,7))
                    w.grid[first['raw_action']] = color
                    w.grid[index(8,7)] = 3-color
                    second = instance.call(encode(w,color-1))
                    self.assertIsNone(second['fault']); self.assertEqual(second['raw_action'],index(7,6))
                    w.grid[second['raw_action']] = color
                    for defend, win in ((4,9),(9,4)):
                        w.grid[index(7,defend)] = 3-color
                        final = instance.call(encode(w,color-1))
                        self.assertIsNone(final['fault']); self.assertEqual(final['raw_action'],index(7,win))
                        w.grid[index(7,defend)] = 0
                    # A promising attack must yield to the opponent's immediate win.
                    w = World()
                    for x,y in ((4,7),(5,7),(6,7),(7,5),(7,8)): w.grid[index(x,y)] = color
                    w.grid[index(3,7)] = 3-color
                    w.grid[index(1,11)] = color
                    for x in (2,3,4,5): w.grid[index(x,11)] = 3-color
                    if color == 2: w.moves = [dict(x=index(3,7)%15,y=index(3,7)//15,color=1)]
                    defense = instance.call(encode(w,color-1))
                    self.assertIsNone(defense['fault']); self.assertEqual(defense['raw_action'],index(6,11))
        finally: instance.close()

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

    def test_bomberman_corner_trap_and_body_block(self):
        instance = self.backend.instance(self.backend.load(self.paths['bomberman','baseline']),1)
        def room(floors, positions):
            grid = [HARD_WALL]*49
            for x,y in floors: grid[y*7+x] = FLOOR
            return BombWorld(7,7,grid,[Player(i,*p) for i,p in enumerate(positions)])
        try:
            trap = room(((3,3),(3,2),(2,2),(2,1),(4,3),(5,3)),((3,3),(5,3)))
            call = instance.call(bomb_encode(trap,0))
            self.assertIsNone(call['fault']); self.assertEqual(call['raw_action'],5)
            hold = room(((5,1),(5,2),(5,3),(4,3),(4,2),(3,3)),((4,2),(5,3)))
            hold.bombs = [Bomb(0,0,3,3,2,3),Bomb(1,1,5,1,2,3)]
            hold.next_bomb_id = 2
            call = instance.call(bomb_encode(hold,0))
            self.assertIsNone(call['fault']); self.assertEqual(call['raw_action'],0)
            # Exhaust every opponent action sequence through detonation.
            import itertools
            for actions in itertools.product(range(6), repeat=3):
                world = deepcopy(hold)
                for action in actions:
                    own = instance.call(bomb_encode(world,0))
                    self.assertIsNone(own['fault']); self.assertEqual(own['raw_action'],0)
                    bomb_step(world,{0:own,1:dict(raw_action=action,fault=None)})
                self.assertTrue(world.players[0].alive)
                self.assertFalse(world.players[1].alive)
                self.assertEqual(world.players[0].score,3+100*world.players[0].kills)
        finally: instance.close()

    def test_bomberman_compact_forecast_matches_engine_chain_closure(self):
        # Query the current C++ predictor; Python's actual explosion closure is the oracle.
        source = self.root / 'forecast-probe.cpp'
        source.write_text(
            '#include "'+(ROOT/'bots/baselines/champion.hpp').as_posix()+'"\n'
            'champion::Forecast prediction;\n'
            'namespace bot {void init(uint64_t) {} Action tick(const GameState& s) {'
            'champion::prepare(s);prediction=champion::forecast(s);return Action::WAIT;}}\n'
            'extern "C" __attribute__((export_name("cell"))) int cell(int i,int t) {'
            'return int(bool(prediction.danger[i]&(1u<<t)))|'
            '(int(prediction.open[i]<=t)<<1)|(int(prediction.until[i]>t)<<2);}\n',
            encoding='utf-8')
        wasm = self.root / 'forecast-probe.wasm'; compile_bot(source,wasm)
        instance = self.backend.instance(self.backend.load(wasm),1)
        rng = random.Random(628129)
        try:
            for trial in range(24):
                grid = [FLOOR]*49
                for y in range(7):
                    for x in range(7):
                        if x in (0,6) or y in (0,6):grid[y*7+x]=HARD_WALL
                        elif rng.random()<.3:grid[y*7+x]=SOFT_WALL
                positions = rng.sample([i for i in range(49) if grid[i]!=HARD_WALL],8)
                for i in positions: grid[i] = FLOOR
                world = BombWorld(7,7,grid,[Player(k,i%7,i//7) for k,i in enumerate(positions)])
                world.bombs = [Bomb(k,k,i%7,i//7,rng.randrange(7),rng.randrange(1,5)) for k,i in enumerate(positions)]
                call = instance.call(bomb_encode(world,0)); self.assertIsNone(call['fault'])
                for t in range(7):
                    occupied = {(b.x,b.y) for b in world.bombs}
                    detonated, soft, coverage = explode(world,[b.id for b in world.bombs if b.explode_at_tick<=t])
                    for i in range(49):
                        x,y = i%7,i//7
                        expected = int((x,y) in coverage)|(int(world.grid[i]==FLOOR)<<1)|(int((x,y) in occupied)<<2)
                        self.assertEqual(instance.exports['cell'](instance.store,i,t),expected,(trial,t,x,y))
                    for x,y in soft:world.grid[y*7+x] = FLOOR
                    world.bombs = [b for b in world.bombs if b.id not in detonated]
        finally: instance.close()
