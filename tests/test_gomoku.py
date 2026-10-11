import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gomoku import MOVE_FUEL
from gomoku.rules import World, opening
from gomoku.match import run_match, qualify
from runner.compiler import compile_bot
from runner.io import ROOT
from replay.verify import verify_world, verify_bot
from service.replays import project
from runtime.wasm import Backend, InfrastructureError
from tests.test_runtime import module


def call(action, fault=None):
    return dict(raw_action=action, fault=fault, fuel_used=10)


class GomokuRulesTests(unittest.TestCase):
    def test_four_directions_and_overline(self):
        for dx, dy in ((1,0),(0,1),(1,1),(1,-1)):
            for n in (5,6):
                w=World()
                for k in range(n-1):
                    w.grid[(7+k*dy)*15+3+k*dx]=1
                w.step({0:call((7+(n-1)*dy)*15+3+(n-1)*dx)})
                self.assertEqual(w.reason,'five_in_row');self.assertEqual(w.winner,0)
                self.assertEqual(len(w.winning_line),n)

    def test_faults_resign_and_occupied(self):
        for action,fault,reason in ((-1,None,'bot_fault'),(226,None,'bot_fault'),(None,'fuel','bot_fault'),
                                    (None,'trap','bot_fault'),(225,None,'resignation')):
            w=World();w.step({0:call(action,fault)})
            self.assertEqual(w.reason,reason);self.assertEqual(w.winner,1)
        w=World();w.step({0:call(112)});w.step({1:call(112)})
        self.assertEqual(w.reason,'illegal_move');self.assertEqual(w.winner,0)
        with self.assertRaises(ValueError): w.step({0:call(0)})

    def test_full_board_and_win_before_draw(self):
        # Two-column bands alternating each row have no five in any direction.
        w=World()
        w.grid=[1+((x//2+y)%2) for y in range(15) for x in range(15)]
        i=next(i for i,c in enumerate(w.grid) if c==1)
        w.grid[i]=0;w.moves=[{}]*224
        w.step({0:call(i)})
        self.assertEqual(w.reason,'board_full');self.assertIsNone(w.winner)
        w=World();w.grid=[2]*225;w.grid[0]=0;w.moves=[{}]*224
        for i in range(1,5):w.grid[i]=1
        w.step({0:call(0)});self.assertEqual(w.reason,'five_in_row')

    def test_opening_library_and_turn(self):
        signatures=set()
        for seed in range(12):
            moves=opening(seed,'library');w=World(moves)
            self.assertEqual(w.turn_id,1);self.assertEqual(w.tick,0)
            signatures.add(str(moves))
        self.assertEqual(len(signatures),12)
        self.assertEqual(opening(5,'empty'),[])
        with self.assertRaises(ValueError):opening(-1,'library')


class GomokuPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def bots(self,bodies):
        out=[]
        for i,(body,init) in enumerate(bodies):
            p=self.root/f'{i}.wasm';p.write_bytes(module(body,init));out.append(dict(id=f'b{i}',wasm=str(p)))
        return out
    def test_replay_rerun_partial_and_tampering(self):
        bots=self.bots([('i32.const 112',''),('i32.const 113','')])
        with Backend() as b:
            qualify(b,bots[0]['wasm'])
            r,records=run_match(b,bots,3,[1,2],opening_mode='library')
            self.assertTrue(r['valid']);verify_world(records);verify_bot(b,records,[e['wasm'] for e in bots])
        self.assertTrue(project(records)['verified'])
        self.assertIsNone(project(records[:-1],partial=True)['result'])
        for pos,key,value in ((1,'after_hash','bad'),(-1,'winner',None),(0,'map_seed',4)):
            changed=copy.deepcopy(records);changed[pos][key]=value
            with self.assertRaises(ValueError):project(changed)
    def test_initialization_and_fuel_failures(self):
        with Backend() as b:
            for bodies,scores in (([('i32.const 0','unreachable')]*2,[.5,.5]),
                                  ([('i32.const 0','unreachable'),('i32.const 0','')],[0,1]),
                                  ([('(loop $l br $l) i32.const 0',''),('i32.const 0','')],[0,1])):
                r,records=run_match(b,self.bots(bodies),0,[1,2])
                self.assertEqual([p['placement_score'] for p in r['players']],scores);verify_world(records)
    def test_infrastructure_failure_is_invalid(self):
        bots=self.bots([('i32.const 0','')]*2)
        with Backend() as b,patch.object(b,'instance',side_effect=InfrastructureError('watchdog')):
            r,records=run_match(b,bots,0,[1,2])
        self.assertFalse(r['valid']);self.assertFalse(project(records)['verified'])
    def test_cpp_baselines_budget_and_tactics(self):
        from gomoku.match import encode
        with Backend() as b:
            for name in ('random','tactical','search'):
                p=self.root/f'{name}.wasm';compile_bot(ROOT/f'bots/gomoku/{name}.cpp',p,'gomoku');qualify(b,p)
                instance=b.instance(b.load(p),1,tick_fuel=MOVE_FUEL);instance.action_max=225
                try:
                    for count in (0,12,60,120):
                        w=World();w.grid=[0]*225
                        for i in range(count):w.grid[i]=1+(i//2+i//15)%2
                        w.moves=[dict(x=i%15,y=i//15,color=w.grid[i]) for i in range(count)]
                        c=instance.call(encode(w,0));self.assertIsNone(c['fault'],(name,count,c));self.assertEqual(w.grid[c['raw_action']],0)
                    if name!='random':
                        w=World();w.grid[105:109]=[1]*4
                        c=instance.call(encode(w,0));self.assertIn(c['raw_action'],(104,109))
                        w.grid[105:109]=[2]*4
                        c=instance.call(encode(w,0));self.assertIn(c['raw_action'],(104,109))
                finally:instance.close()

    def test_baseline_full_games_across_every_opening_and_color(self):
        with Backend() as b:
            bots=[]
            for name in ('tactical','search'):
                p=self.root/f'{name}.wasm';compile_bot(ROOT/f'bots/gomoku/{name}.cpp',p,'gomoku')
                bots.append(dict(id=name,wasm=str(p)))
            for seed in range(12):
                for swap in (False,True):
                    with self.subTest(seed=seed,swap=swap):
                        r,records=run_match(b,bots[::-1] if swap else bots,seed,[2,1] if swap else [1,2],opening_mode='library')
                        self.assertIn(r['reason'],('five_in_row','board_full'));verify_world(records)
                        self.assertTrue(all(not c['fault'] for t in records for c in t.get('calls',[])))
