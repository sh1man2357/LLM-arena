"""Verify raw frozen inputs behind the actual final Chrome-created hidden batch."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runner.io import ROOT,read_json,sha_file,write_json
from runner.tournament import schedule
from service.store import Store

def main():
    evidence=ROOT/'artifacts/acceptance/v0.2-development/final/checks'
    proof=read_json(evidence/'runtime-api.json')
    store=Store(ROOT/'artifacts/work/v0.2-final-01')
    job=store.get('job',proof['job']['id'])
    inputs=job['inputs'];batch=store.get('tournament',inputs['tournament_id'])
    folder=Path(batch['directory']);manifest=read_json(folder/'manifest.json')
    cases=read_json(folder/'cases.json');plan=read_json(folder/'schedule.json')
    assert cases==inputs['cases']
    assert plan==schedule(inputs['entrants'],cases)
    assert [dict(id=e['id'],wasm_sha256=e['wasm_sha256']) for e in manifest['entrants']]==[dict(id=e['id'],wasm_sha256=e['wasm_sha256']) for e in inputs['entrants']]
    rows=[]
    for item in plan:
        record=store.get('match',batch['id']+'-'+item['match_id'])
        header=json.loads(Path(record['replay']).read_bytes().splitlines()[0])
        assert header['map_seed']==item['map_seed']
        assert header['bot_seeds']==item['bot_seeds']
        assert [e['id'] for e in header['entrants']]==item['entrants']
        assert [e['wasm_sha256'] for e in header['entrants']]==[next(e['wasm_sha256'] for e in inputs['entrants'] if e['id']==identity) for identity in item['entrants']]
        rows.append(dict(id=record['id'],replay_sha256=sha_file(record['replay']),swapped=item['swapped'],entrant_seed=dict(zip(item['entrants'],item['bot_seeds']))))
    assert rows[0]['entrant_seed']==rows[1]['entrant_seed']
    write_json(evidence/'runtime-frozen.json',dict(status='passed',job_id=job['id'],batch_id=batch['id'],matches=rows,
        source=dict(manifest_sha256=sha_file(folder/'manifest.json'),cases_sha256=sha_file(folder/'cases.json'),schedule_sha256=sha_file(folder/'schedule.json')),
        checks=['actual UI-created pool equals frozen manifest','actual cases and schedule equal job snapshot','all raw Replay header maps/seeds/WASM agree','Bot Seed follows entrant through swapped slots']))
    print('Verified actual UI-created frozen pool, cases, schedule and both swapped raw Replay headers.')

if __name__=='__main__':main()
