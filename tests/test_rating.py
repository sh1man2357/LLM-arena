from copy import deepcopy
import unittest

from runner.rating import strengths
from service.leaderboard import leaderboard


def run(scores, ids, **extra):
    return dict(status='completed',verified=True,entrants=[dict(id=name,slot=i) for i,name in enumerate(ids)],
                result=dict(valid=True,scoring_version=2,players=[dict(id=i,placement_score=s) for i,s in enumerate(scores)]),**extra)


class RatingTests(unittest.TestCase):
    def setUp(self):
        self.bots=[dict(id=i,name='Baseline' if i=='base' else i,baseline=i=='base',created='2026',status='ready')
                   for i in ('base','strong','weak','island','other')]

    def test_reference_visible_without_matches_and_unconnected_scores_pending(self):
        rows=leaderboard(self.bots,[])['items']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['rating'],0)
        self.assertIsNone(rows[0]['mean_score'])
        rows=leaderboard(self.bots,[run([1,0],['island','other'])])['items']
        self.assertTrue(all(r['rating'] is None and r['rank'] is None for r in rows if r['id']!='base'))

    def test_wins_losses_transitive_links_finite_and_order_independent(self):
        runs=[run([1,0],['strong','base'])]*10+[run([0,1],['weak','base'])]*10
        runs += [run([1,0],['island','strong'])]*10
        result=leaderboard(self.bots,runs)
        scores={r['id']:r['rating'] for r in result['items']}
        self.assertEqual(scores['base'],0);self.assertGreater(scores['strong'],0);self.assertLess(scores['weak'],0)
        self.assertGreater(scores['island'],scores['strong'])
        self.assertEqual(result,leaderboard(self.bots,runs[::-1]))
        self.assertEqual(result,leaderboard(list(reversed(self.bots)),runs))
        self.assertEqual(strengths([('a','base',1,1)]*20,'base')['a'],
                         -strengths([('a','base',0,1)]*20,'base')['a'])

    def test_multiplayer_weights_selfplay_and_equal_strength(self):
        two=leaderboard(self.bots,[run([1,0],['strong','base'])])
        eight=leaderboard(self.bots,[run([1]+[3/7]*7,['strong']+['base']*7)])
        self.assertEqual({r['id']:r['rating'] for r in two['items']},{r['id']:r['rating'] for r in eight['items']})
        draws=leaderboard(self.bots,[run([.5,.5],['strong','base']),run([1,0],['strong','strong'])])
        self.assertEqual([r['rating'] for r in draws['items']],[0,0])
        self.assertEqual([r['rank'] for r in draws['items']],[1,1])

    def test_failed_invalid_records_do_not_calibrate_and_retired_references_hidden(self):
        invalid=run([1,0],['strong','base']);invalid['verified']=False
        retired={**self.bots[0],'id':'retired','name':'Heuristic'}
        rows=leaderboard([*self.bots,retired],[invalid,run([1,0],['strong','retired'])])['items']
        self.assertNotIn('retired',[r['id'] for r in rows])
        self.assertIsNone(next(r for r in rows if r['id']=='strong')['rating'])
        latest={**self.bots[0],'id':'new-base','created':'2027'}
        rows=leaderboard([*self.bots,latest],[run([1,0],['strong','base'])])['items']
        self.assertNotIn('base',[r['id'] for r in rows]);self.assertIsNone(next(r for r in rows if r['id']=='strong')['rating'])

    def test_gomoku_incomplete_pair_has_no_strength_evidence(self):
        bots=[{**b,'game_id':'gomoku'} for b in self.bots]
        first=run([1,0],['strong','base'],id='first',task_id='task',map_seed=2,opening_mode='library',game_id='gomoku',pair_runs=['first','swap'],pair_id='first',pair_index=0)
        second=run([0,1],['base','strong'],id='swap',task_id='task',map_seed=2,opening_mode='library',game_id='gomoku',pair_runs=['first','swap'],pair_id='first',pair_index=1)
        self.assertEqual(len(leaderboard(bots,[first],'gomoku')['items']),1)
        full=leaderboard(bots,[first,second],'gomoku')
        self.assertGreater(next(r for r in full['items'] if r['id']=='strong')['rating'],0)
        broken=deepcopy(second);broken['status']='failed'
        self.assertEqual(len(leaderboard(bots,[first,broken],'gomoku')['items']),1)

    def test_legacy_bomberman_results_never_enter_new_ratings(self):
        legacy = run([1, 0], ['strong', 'base'])
        del legacy['result']['scoring_version']
        self.assertEqual(leaderboard(self.bots, [legacy])['valid_matches'], 0)
        self.assertEqual(leaderboard(self.bots, [legacy, run([.5, .5], ['strong', 'base'])])['valid_matches'], 1)

