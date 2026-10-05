"""Verified old/current batches plus actual fault/tie WASM competition cases."""
import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT, read_json, sha_file, write_json
from runner.tournament import run_tournament
from runner.report import generate_report
from replay.verify import read
from service.imports import import_bundled, import_tournament, extract_archive, remap_report
from service.store import Store
from service.analysis import summarize
from service.publication import close_submissions
from tests.test_runtime import module


def raw_analysis(folder):
    """Count original event/action records without the spectator facts implementation."""
    reasons, draw_reasons, actions, faults, stats = [Counter() for _ in range(5)]
    moves = blocked = quiet = longest = 0
    patterns = dict(no_bomb=0, no_successful_move=0, with_fault=0, with_explosion_death=0)
    traces = []
    for item in read_json(folder/'schedule.json'):
        path = folder/'replays'/f"{item['match_id']}.jsonl"
        records = read(path); result = records[-1]
        assert result['valid']
        reasons[result['reason']] += 1
        draw = all(p['placement_score'] == .5 for p in result['players'])
        if draw:
            draw_reasons[result['reason']] += 1
            patterns['no_bomb'] += sum(s['bombs_placed'] for s in result['stats']) == 0
            patterns['with_fault'] += any(s['action_faults']+s['runtime_eliminations']+s['initialization_failures'] for s in result['stats'])
            patterns['with_explosion_death'] += any(s['explosion_deaths'] for s in result['stats'])
        for player in result['stats']:
            for key,value in player.items():
                stats[key] = max(stats[key],value) if key=='max_tick_fuel' else stats[key]+value
        prior = records[0]['initial_state']; run = match_moves = 0
        for record in records[1:-1]:
            moved = {e['player'] for e in record['events'] if e['type']=='move'}
            match_moves += len(moved)
            blocked += sum(a['action'] in [1,2,3,4] and a['id'] not in moved for a in record['actions'])
            actions.update(str(a['action']) for a in record['actions'])
            faults.update(c['fault'] for c in record['calls'] if c.get('fault'))
            state = record['state']
            same = not prior['bombs'] and not state['bombs'] and {k:v for k,v in prior.items() if k!='tick'} == {k:v for k,v in state.items() if k!='tick'}
            quiet += same; run = run+1 if same else 0; longest = max(longest,run); prior=state
        moves += match_moves
        if draw: patterns['no_successful_move'] += match_moves==0
        traces.append(dict(match_id=item['match_id'],sha256=sha_file(path),ticks=result['ticks'],draw=draw,quiet_tail_ticks=run))
    expected = dict(matches=len(traces),reasons=dict(sorted(reasons.items())),draws=sum(draw_reasons.values()),
                    draw_reasons=dict(sorted(draw_reasons.items())),stats=dict(sorted(stats.items())),
                    actions=dict(sorted(actions.items())),call_faults=dict(sorted(faults.items())),
                    bombs_placed=stats['bombs_placed'],moves=moves,blocked_moves=blocked,waits=actions['0'],
                    quiet_ticks=quiet,longest_quiet_run=longest,draw_patterns=patterns)
    return expected,traces


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--data',required=True); parser.add_argument('--proof',required=True)
    args=parser.parse_args(); root=Path(args.data).resolve()
    if root.exists(): raise ValueError('Use a fresh report-check directory')
    store=Store(root); old=import_bundled(store)
    archive=ROOT/'artifacts/acceptance/v0.2-baselines/evidence.zip'
    assert sha_file(archive)==read_json(archive.with_name('evidence.index.json'))['sha256']
    current=root/'current-baselines';extract_archive(archive,current)
    new=import_tournament(store,current,'report-baselines-v02',title='当前 SDK 三 Baseline · 300 局工程检查')
    new=close_submissions(store,new['id'])
    batch=root/'fault-tie';batch.mkdir();(batch/'build').mkdir()
    gate='i32.const 0 i32.load offset=4 i32.const 5 i32.ge_u'
    modules={'wait-a':module(),'wait-b':module(),
             'fuel':module(gate+' if (loop $l br $l) end i32.const 0'),
             'invalid':module(gate+' if (result i32) i32.const 99 else i32.const 0 end'),
             'trap':module(gate+' if unreachable end i32.const 0'),
             'init':module(init='local.get 0 i32.const 1 i32.gt_u if unreachable end')}
    entrants=[]
    for name,code in sorted(modules.items()):
        path=batch/'build'/f'{name}.wasm';path.write_bytes(code);entrants.append(dict(id=name,wasm=str(path)))
    cases=[dict(map_seed=seed,bot_seeds=['0000000000000002','0000000000000003']) for seed in [1,2,3]]
    run_tournament(entrants,cases,batch); generate_report(batch)
    fault=import_tournament(store,batch,'report-fault-tie',title='实际 WASM 故障与并列 · 工程检查')
    fault=close_submissions(store,fault['id'])
    for entrant in fault['entrant_aliases'].values():
        store.update('entrant',entrant,lambda r:r.update(model='工程 WASM 报告检查，不是模型提交'))
    proofs=[]
    for row in [old,new,fault]:
        folder=Path(row['directory']); expected,traces=raw_analysis(folder)
        actual=summarize([m for m in store.list('match') if m.get('tournament_id')==row['id']])
        assert all(actual[k]==v for k,v in expected.items()), (row['id'],expected,actual)
        assert row['report']==remap_report(read_json(folder/'report.json'),row['entrant_aliases'])
        proofs.append(dict(id=row['id'],report=row['report'],expected_analysis=expected,
                           source_report_sha256=sha_file(folder/'report.json'),traces=traces))
    write_json(args.proof,dict(kind='verified_reports_and_raw_trace_comparison',batches=proofs))
    print(f'Verified reports and independently counted {sum(p["expected_analysis"]["matches"] for p in proofs)} original traces.')


if __name__=='__main__':main()
