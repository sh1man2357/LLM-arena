from concurrent.futures import ThreadPoolExecutor
import copy
import threading
import unittest
from unittest.mock import patch

from runner.io import sha_file
from runner.match import components
from service.app import create_app
from service.bots import manage_bots
from tests import test_service

HEADERS = test_service.HEADERS


class BotManagementTests(unittest.TestCase):
    setUp = test_service.CoreServiceTests.setUp
    tearDown = test_service.CoreServiceTests.tearDown
    add_bot = test_service.CoreServiceTests.add_bot
    start_run = test_service.CoreServiceTests.start_run
    finish = test_service.CoreServiceTests.finish

    def edit(self, identity, **fields):
        return self.client.patch(f'/api/v1/bots/{identity}', headers=HEADERS, json=fields)

    def manage(self, action, ids):
        return self.client.post('/api/v1/bots/manage', headers=HEADERS, json=dict(action=action, ids=ids))

    def test_edit_partial_fields_preserves_snapshots_and_updates_future_names(self):
        original = copy.deepcopy(self.store.get('bot', 'a'))
        run = self.start_run().json()
        changed = self.edit('a', name=' 新名称 ', description=' 模型 X\n策略 v2 ')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual((changed.json()['name'], changed.json()['description']), ('新名称', '模型 X\n策略 v2'))
        row = self.store.get('bot', 'a')
        for key, value in original.items():
            if key != 'name':
                self.assertEqual(row[key], value)
        self.assertEqual(self.store.get('run', run['id'])['entrants'][0]['name'], 'a')
        self.assertTrue(self.finish(run)['verified'])
        snapshot = self.store.get('task', self.store.get('run', run['id'])['task_id'])['inputs']
        self.assertEqual(snapshot['entrants'][0]['name'], 'a')
        self.assertEqual(self.edit('a', description='').json()['description'], '')
        self.assertEqual(self.store.get('bot', 'a')['name'], '新名称')
        next_run = self.start_run(key='next').json()
        self.assertEqual(next_run['entrants'][0]['name'], '新名称')
        rankings = self.client.get('/api/v1/leaderboard').json()['items']
        self.assertEqual(next(row for row in rankings if row['id'] == 'a')['name'], '新名称')
        # Reopening the database retains edits without touching recordings.
        self.assertEqual(create_app(self.root).state.store.get('bot', 'a')['description'], '')

    def test_trash_restore_keeps_files_replays_and_rating_evidence(self):
        run = self.start_run().json()
        self.finish(run)
        before = self.client.get('/api/v1/leaderboard').json()
        original = self.store.get('bot', 'b')
        self.assertEqual(self.manage('trash', ['b', 'b']).json(), dict(changed=1))
        self.assertEqual([b['id'] for b in self.client.get('/api/v1/bots').json()['items']], ['a'])
        self.assertEqual([b['id'] for b in self.client.get('/api/v1/bots?trashed=true').json()['items']], ['b'])
        self.assertEqual(sha_file(original['wasm']), original['wasm_sha256'])
        self.assertTrue(self.client.get(f"/api/v1/matches/{run['id']}/frames").json()['verified'])
        self.assertEqual(self.start_run(key='deleted').status_code, 409)
        self.assertEqual(self.client.post(f"/api/v1/matches/{run['id']}/rerun", headers=HEADERS).status_code, 409)
        scores = self.client.get('/api/v1/leaderboard').json()
        self.assertEqual(scores['valid_matches'], before['valid_matches'])
        self.assertEqual(scores['items'], [b for b in before['items'] if b['id'] != 'b'])
        self.assertEqual(self.edit('b', name='hidden').status_code, 404)
        self.assertEqual(self.manage('trash', ['b']).json(), dict(changed=0))
        self.assertEqual(self.manage('restore', ['b']).json(), dict(changed=1))
        self.assertEqual(self.manage('restore', ['b']).json(), dict(changed=0))
        self.assertEqual(self.client.get('/api/v1/bots?trashed=true').json()['items'], [])
        self.assertEqual(self.client.get('/api/v1/leaderboard').json(), before)
        self.assertEqual(self.start_run(key='restored').status_code, 202)

    def test_validation_local_boundary_baseline_and_compilation_protection(self):
        for fields in ({}, dict(name='  '), dict(name='x'*101), dict(description='x'*1001),
                       dict(name=None), dict(description=None), dict(game_id='gomoku'), dict(baseline=True), dict(wasm='elsewhere')):
            self.assertEqual(self.edit('a', **fields).status_code, 422, fields)
        self.assertEqual(self.edit('missing', name='No').status_code, 404)
        self.assertEqual(self.client.patch('/api/v1/bots/a', json=dict(name='No')).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/bots/manage', json=dict(action='trash', ids=['a'])).status_code, 403)
        for fields in (dict(action='delete', ids=['a']), dict(action='trash', ids=[]), dict(action='trash', ids=['a']*101)):
            self.assertEqual(self.client.post('/api/v1/bots/manage', headers=HEADERS, json=fields).status_code, 422)
        self.store.update('bot', 'b', lambda b: b.update(baseline=True, name='Baseline'))
        self.assertEqual(self.edit('b', name='No').status_code, 409)
        self.assertEqual(self.manage('trash', ['a', 'b']).status_code, 409)
        self.assertFalse(self.store.get('bot', 'a').get('deleted_at'))
        self.store.update('bot', 'b', lambda b: b.update(baseline=False, status='processing'))
        self.assertEqual(self.edit('b', description='No').status_code, 409)
        self.assertEqual(self.manage('trash', ['a', 'b']).status_code, 409)
        self.assertFalse(self.store.get('bot', 'a').get('deleted_at'))
        self.assertEqual(self.manage('trash', ['a', 'missing']).status_code, 404)
        self.assertFalse(self.store.get('bot', 'a').get('deleted_at'))

    def test_active_match_and_human_match_cannot_lose_bot(self):
        run = self.start_run().json()
        self.assertTrue(all(b['in_use'] for b in self.client.get('/api/v1/bots').json()['items']))
        self.assertEqual(self.manage('trash', ['a']).status_code, 409)
        self.finish(run)
        self.assertTrue(all(not b['in_use'] for b in self.client.get('/api/v1/bots').json()['items']))
        self.store.update('bot', 'a', lambda b: b.update(game_id='gomoku'))
        response = self.client.post('/api/v1/human-matches', headers=HEADERS, json=dict(bot_id='a'))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.manage('trash', ['b', 'a']).status_code, 409)
        self.assertFalse(self.store.get('bot', 'b').get('deleted_at'))
        self.app.state.executor.recover_interrupted()
        self.assertEqual(self.manage('trash', ['a']).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/human-matches', headers=HEADERS, json=dict(bot_id='a')).status_code, 409)

    def test_start_rechecks_bot_after_freezing_before_task_transaction(self):
        def delete_during_preparation(*args):
            manage_bots(self.store, 'trash', ['b'])
            return components(*args)
        with patch('service.app.components', side_effect=delete_during_preparation):
            self.assertEqual(self.start_run().status_code, 409)
        self.assertFalse(self.store.list('run'))
        self.assertFalse(self.store.list('task'))

    def test_competing_delete_and_start_cannot_both_succeed(self):
        barrier = threading.Barrier(2)
        def start():
            barrier.wait()
            return self.start_run().status_code
        def delete():
            barrier.wait()
            return self.manage('trash', ['b']).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(start), pool.submit(delete)
            statuses = first.result(), second.result()
        self.assertIn(statuses, ((202, 409), (409, 200)))
        if statuses[0] == 202:
            self.assertFalse(self.store.get('bot', 'b').get('deleted_at'))
        else:
            self.assertFalse(self.store.list('run'))
