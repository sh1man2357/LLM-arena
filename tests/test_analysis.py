import copy
from pathlib import Path
import tempfile
import unittest

from runner.io import write_json
from service.analysis import trace_facts, summarize


class TraceAnalysisTests(unittest.TestCase):
    def frame(self, tick, bombs=None, fault=0, action=0):
        return dict(state=dict(tick=tick,grid=[0],players=[dict(alive=True)],bombs=bombs or [],fault_counters=[fault]),
                    actions=[dict(id=0,action=action)],calls=[dict(fault=None)],
                    events=[],visual=dict(blocked_moves=[0] if action==1 else []))

    def test_quiet_ticks_exclude_bomb_countdown_and_fault_changes(self):
        frames=[self.frame(0),self.frame(1,action=1),self.frame(2,[dict(id=0)]),
                self.frame(3,[dict(id=0)]),self.frame(4),self.frame(5,fault=1),
                self.frame(6,fault=1),self.frame(7,fault=1)]
        facts=trace_facts(dict(frames=frames))
        self.assertEqual((facts['quiet_ticks'],facts['longest_quiet_run'],facts['quiet_tail_ticks']),(3,2,2))
        self.assertEqual(facts['blocked_moves'],1)

    def test_legacy_facts_are_derived_without_changing_projection_or_index(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'projection.json'
            ui=dict(source_sha256='a'*64,verified=True,frames=[self.frame(0),self.frame(1)])
            write_json(path,ui); original=path.read_bytes()
            stats=dict(calls=1,max_tick_fuel=5,bombs_placed=0,action_faults=0,runtime_eliminations=0,initialization_failures=0,explosion_deaths=0)
            row=dict(id='m',entrants=[dict(id='a'),dict(id='b')],status='completed',verified=True,projection=str(path),source_sha256='a'*64,facts=dict(moves=0),
                     result=dict(valid=True,reason='tick_limit',ticks=1,players=[dict(placement_score=.5)]*2,stats=[stats,stats]))
            frozen=copy.deepcopy(row); failed=copy.deepcopy(row);failed.update(id='failed',status='failed')
            result=summarize([row,failed]);self.assertEqual(result['matches'],1);self.assertEqual(result['excluded_matches'],1)
            self.assertEqual(result['stats']['max_tick_fuel'],5)
            self.assertEqual(result['quiet_ticks'],1);self.assertEqual(row,frozen);self.assertEqual(path.read_bytes(),original)
            row['source_sha256']='b'*64
            with self.assertRaises(ValueError): summarize([row])
            row['projection']=str(Path(directory)/'missing.json')
            result=summarize([row]);self.assertEqual(result['facts_unavailable'],['m']);self.assertEqual(result['facts_matches'],0)


if __name__=='__main__':unittest.main()
