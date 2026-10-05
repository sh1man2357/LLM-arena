"""Release disclosure, local requests and frozen scheduling boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from fastapi.testclient import TestClient
from runner.io import ROOT
from runner.tournament import schedule
from service.app import create_app
from service.imports import import_tournament
from tests.test_import_publication import fixture


class ReleaseBoundaries(unittest.TestCase):
    def test_sealed_routes_lists_and_publication_disclosure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root / 'legacy', wasm=False)
            app = create_app(root / 'data')
            batch = import_tournament(app.state.store, root / 'legacy', 'release-sealed')
            matches = app.state.store.list('match')
            with TestClient(app) as client:
                private = [f'/api/v1/tournaments/{batch["id"]}{suffix}' for suffix in ('','/report','/analysis')]
                private += [f'/api/v1/exports/{batch["id"]}?kind={kind}' for kind in ('report','publication')]
                for match in matches:
                    private += [f'/api/v1/matches/{match["id"]}',f'/api/v1/matches/{match["id"]}/frames',f'/api/v1/exports/{match["id"]}']
                for url in private:
                    self.assertEqual(client.get(url).status_code,403,url)
                self.assertEqual(client.get('/api/v1/tournaments').json()['items'],[])
                self.assertEqual(client.get('/api/v1/matches').json()['total'],0)
                client.post('/api/v1/admin/unlock',headers={'x-arena-local':'1'})
                self.assertEqual(client.post(f'/api/v1/tournaments/{batch["id"]}/publish').status_code,409)
                closed = client.post(f'/api/v1/tournaments/{batch["id"]}/close-submissions').json()
                self.assertEqual(closed['window_close_source'],'host_confirmation')
                client.post(f'/api/v1/tournaments/{batch["id"]}/publish').raise_for_status()
                client.cookies.clear()
                for url in private:
                    response = client.get(url)
                    self.assertEqual(response.status_code,200,url)
                    for marker in ('"bot_seeds"','"map_seed"','"source_files"','"diagnostic"',str(root)):
                        self.assertNotIn(marker,response.text,url)

    def test_local_request_and_input_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(folder)) as client:
                for headers in ({'host':'remote.test'},{'origin':'https://remote.test'},{'sec-fetch-site':'cross-site'}):
                    self.assertEqual(client.post('/api/v1/admin/unlock',headers={**headers,'x-arena-local':'1'}).status_code,403)
                self.assertEqual(client.post('/api/v1/admin/unlock').status_code,403)
                client.post('/api/v1/admin/unlock',headers={'x-arena-local':'1'})
                response = client.get('/health')
                self.assertEqual(response.headers['x-content-type-options'],'nosniff')
                self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
                self.assertEqual(client.post('/api/v1/sessions',json={'name':'x','source_path':'../../private'}).status_code,422)
                session = client.post('/api/v1/sessions',json={'name':'<script>literal</script>'}).json()
                self.assertEqual(client.post(f'/api/v1/sessions/{session["id"]}/submit',json={'source':'中'*(1024*1024//3+1)}).status_code,413)
                self.assertEqual(client.post('/api/v1/imports/replay',files={'file':('x',b'x'*(16*1024*1024+1))}).status_code,413)
                self.assertEqual(client.post('/api/v1/imports/archive',files={'file':('x',b'x'*(16*1024*1024+1))}).status_code,413)
                self.assertEqual(client.post('/api/v1/sessions',content=b'{}',headers={'content-length':str(18*1024*1024+1)}).status_code,413)
                source = client.post(f'/api/v1/sessions/{session["id"]}/submit',json={'source':'<script>literal source</script>'}).json()
                raw = client.get(f'/api/v1/submissions/{source["id"]}/source')
                self.assertIn('text/plain',raw.headers['content-type'])
                self.assertEqual(raw.text,'<script>literal source</script>')
                self.assertNotIn('literal source',client.get('/submissions/'+source['id']+'/bot.cpp').text)

    def test_api_freezes_pool_cases_and_seed_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            store = app.state.store
            with zipfile.ZipFile(ROOT/'artifacts/acceptance/v0.1-release/evidence.zip') as archive:
                for identity in ('safe','random','heuristic'):
                    wasm = Path(folder)/(identity+'.wasm'); wasm.write_bytes(archive.read(f'build/{identity}.wasm'))
                    from runner.io import sha_file
                    store.put('entrant',dict(id=identity,name=identity,status='qualified',wasm=str(wasm),wasm_sha256=sha_file(wasm)))
            with TestClient(app) as client:
                client.post('/api/v1/admin/unlock',headers={'x-arena-local':'1'})
                body = dict(entrant_ids=['safe','random','heuristic'],case_count=3,official=True,title='frozen')
                key = {'idempotency-key':'freeze-cases'}
                first = client.post('/api/v1/tournaments',json=body,headers=key).json()
                inputs = store.get('job',first['id'])['inputs']
                self.assertEqual(client.post('/api/v1/tournaments',json=body,headers=key).json()['id'],first['id'])
                self.assertEqual(store.get('job',first['id'])['inputs'],inputs)
                self.assertEqual(len(schedule(inputs['entrants'],inputs['cases'])),18)
                for case in inputs['cases']:
                    self.assertTrue(all(len(seed)==16 for seed in case['bot_seeds']))
                plan = schedule(inputs['entrants'],inputs['cases'])
                for left,right in zip(plan[::2],plan[1::2]):
                    self.assertEqual(dict(zip(left['entrants'],left['bot_seeds'])),dict(zip(right['entrants'],right['bot_seeds'])))
                store.update('entrant','safe',lambda r:r.update(wasm_sha256='0'*64))
                self.assertNotEqual(store.get('entrant','safe')['wasm_sha256'],next(e['wasm_sha256'] for e in inputs['entrants'] if e['id']=='safe'))
                self.assertEqual(store.get('job',first['id'])['inputs'],inputs)
                self.assertEqual(client.post('/api/v1/tournaments',json={**body,'case_count':4},headers=key).status_code,409)


if __name__ == '__main__':
    unittest.main()
