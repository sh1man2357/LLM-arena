"""Core workflow, snapshot isolation, frames, local boundary and retained ranking."""
from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from runner.io import sha_file
from runner.match import run_match
from runtime.wasm import Backend
from service.app import create_app
from service.bots import import_bot, prepare_baselines
from service.jobs import BusyError, Executor
from service.leaderboard import leaderboard
from service.store import utc_now
from service.worker import LiveSink, main as execute
from tests.test_runtime import module

HEADERS = {'X-Arena-Local': '1'}


class CoreServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root)
        self.store, self.executor = self.app.state.store, self.app.state.executor
        self.client = TestClient(self.app)
        self.add_bot('a'); self.add_bot('b')

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def add_bot(self, identity, code=None):
        path = self.root / f'{identity}.wasm'
        path.write_bytes(code or module())
        row = dict(id=identity, name=identity, status='ready', baseline=False, wasm=str(path),
                   wasm_sha256=sha_file(path), created=utc_now())
        self.store.put('bot', row)
        return row

    def start_run(self, key='one', ids=None, seed=None):
        return self.client.post('/api/v1/matches', headers={**HEADERS, 'Idempotency-Key': key},
                                json={'bot_ids': ids or ['a', 'b'], **({} if seed is None else {'map_seed': seed})})

    def finish(self, run):
        task = self.store.get('run', run['id'])['task_id']
        with patch('service.worker.time.sleep'):
            execute(self.root, task)
        return self.store.get('run', run['id'])

    def test_upload_auto_compiles_real_cpp_without_receipt(self):
        source = b'#include "arena.hpp"\nnamespace bot { void init(uint64_t){} Action tick(const GameState&){return Action::WAIT;} }'
        response = self.client.post('/api/v1/bots', headers={**HEADERS, 'Idempotency-Key': 'upload'},
                                    files={'file': ('bot.cpp', source)}, data={'name': ' Test Bot '})
        self.assertEqual(response.status_code, 202)
        bot = response.json(); self.assertEqual(bot['status'], 'processing')
        task = self.store.list('task')[0]
        execute(self.root, task['id'])
        imported = self.store.get('bot', bot['id'])
        self.assertEqual(imported['status'], 'ready')
        self.assertEqual(imported['name'], 'Test Bot')
        self.assertEqual(Path(imported['source']).read_bytes(), source)
        self.assertFalse(self.store.list('session')); self.assertFalse(self.store.list('submission'))
        replayed = self.client.post('/api/v1/bots', headers={**HEADERS, 'Idempotency-Key': 'upload'},
                                   files={'file': ('bot.cpp', source)}, data={'name': ' Test Bot '})
        self.assertEqual(replayed.json()['id'], bot['id'])
        self.assertEqual(len(self.store.list('task')), 1)

    def test_compile_failure_is_visible_and_frees_slot(self):
        bot = import_bot(self.store, self.executor, b'not valid C++', 'broken')
        with self.assertRaises(ValueError):
            execute(self.root, self.store.list('task')[0]['id'])
        viewed = next(b for b in self.client.get('/api/v1/bots').json()['items'] if b['id'] == bot['id'])
        self.assertEqual(viewed['status'], 'failed')
        self.assertIn('Compilation failed', viewed['diagnostic'])
        self.assertTrue(viewed['compile_log']['stderr'])
        self.assertEqual(self.start_run().status_code, 202)

    def test_upload_validation(self):
        for filename, data in [('bot.wasm', b'wasm'), ('bot.cpp', b''), ('bot.cpp', b'\xff')]:
            response = self.client.post('/api/v1/bots', headers=HEADERS, files={'file': (filename, data)})
            self.assertEqual(response.status_code, 422)
        large = self.client.post('/api/v1/bots', headers=HEADERS,
                                 files={'file': ('large.cpp', b'x' * (1024 * 1024 + 1))})
        self.assertEqual(large.status_code, 413)
        self.assertFalse(self.store.list('task'))

    def test_only_two_ready_slots_can_run(self):
        for ids in ([], ['a'], ['a', 'b', 'a']):
            response = self.client.post('/api/v1/matches', headers=HEADERS, json={'bot_ids': ids})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.start_run(ids=['a', 'missing']).status_code, 404)
        self.store.update('bot', 'b', lambda b: b.update(status='failed'))
        self.assertEqual(self.start_run().status_code, 409)
        self.assertFalse(self.store.list('run'))

    def test_same_bot_can_play_both_slots_and_rerun(self):
        response = self.start_run(ids=['a', 'a'], seed=1)
        self.assertEqual(response.status_code, 202)
        run = response.json()
        self.assertEqual([(e['id'], e['slot']) for e in run['entrants']], [('a', 0), ('a', 1)])
        self.assertTrue(self.finish(run)['verified'])
        frames = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
        self.assertTrue(frames['verified'])
        self.assertEqual(len(frames['frames']), 501)
        scores = self.client.get('/api/v1/leaderboard').json()
        self.assertEqual(scores['valid_matches'], 1)
        self.assertEqual(len(scores['items']), 1)
        row = scores['items'][0]
        self.assertEqual((row['id'], row['matches'], row['draws'], row['mean_score']), ('a', 2, 2, .5))
        response = self.client.post(f"/api/v1/matches/{run['id']}/rerun", headers=HEADERS)
        self.assertEqual(response.status_code, 202)
        rerun = response.json()
        self.assertNotEqual(rerun['id'], run['id'])
        self.assertEqual(rerun['entrants'], run['entrants'])
        inputs = [self.store.get('task', self.store.get('run', r['id'])['task_id'])['inputs']
                  for r in (run, rerun)]
        self.assertEqual(inputs[0]['bot_seeds'], inputs[1]['bot_seeds'])
        self.assertTrue(self.finish(rerun)['verified'])

    def test_handoff_retries_do_not_duplicate_or_reseed(self):
        first = self.start_run().json()
        again = self.start_run().json()
        self.assertEqual(first, again)
        self.assertEqual(len(self.store.list('run')), 1)
        original = copy.deepcopy(self.store.list('task')[0]['inputs'])
        self.assertEqual(self.start_run(key='another').status_code, 409)
        self.assertEqual(self.start_run(ids=['b', 'a']).status_code, 409)
        self.assertEqual(self.store.list('task')[0]['inputs'], original)
        self.assertTrue(self.client.get('/api/v1/status').json()['busy'])

    def test_competing_requests_reserve_only_one_compute_slot(self):
        def submit(index):
            try:
                return self.executor.create('match', {'index': index})
            except BusyError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_spawn_order_and_seed_zero_are_preserved(self):
        run = self.start_run(ids=['b', 'a'], seed=0).json()
        self.assertEqual([e['id'] for e in run['entrants']], ['b', 'a'])
        self.assertEqual(run['map_seed'], 0)
        inputs = self.store.list('task')[0]['inputs']
        self.assertTrue(all(len(seed) == 16 for seed in inputs['bot_seeds']))

    def test_live_and_recording_share_frames_and_reading_never_executes(self):
        run = self.start_run(seed=1).json()
        before = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
        self.assertEqual(before['frames'], [])
        self.finish(run)
        with patch('service.worker.run_match', side_effect=AssertionError('reading must not run Bots')):
            all_frames = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
            delta = self.client.get(f"/api/v1/matches/{run['id']}/frames?after_seq=490").json()
            again = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
        self.assertEqual(all_frames, again)
        self.assertEqual(len(all_frames['frames']), 501)
        self.assertEqual([f['seq'] for f in delta['frames']], list(range(491, 501)))
        self.assertEqual(all_frames['frames'][0]['tick'], None)
        self.assertEqual(all_frames['frames'][-1]['tick'], 499)
        self.assertTrue(all_frames['verified']); self.assertFalse(all_frames['partial'])
        self.assertEqual(all_frames['result']['reason'], 'tick_limit')
        self.assertFalse(self.client.get('/api/v1/status').json()['busy'])

    def test_partial_line_is_not_published_and_terminal_is_withheld(self):
        run = self.start_run(seed=1).json()
        inputs = self.store.list('task')[0]['inputs']
        with Backend() as backend:
            _, records = run_match(backend, inputs['entrants'], 1, [1, 2], run['id'])
        sink = LiveSink(self.store, run['id'])
        self.assertTrue(any(e['resource_id'] == run['id'] and e['payload'].get('status') == 'running'
                            for e in self.store.events()))
        try:
            sink(records[0])
            sink.stream.write('{"type": "tick"'); sink.stream.flush()
            frames = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
            self.assertEqual(len(frames['frames']), 1)
            self.assertIsNone(frames['result']); self.assertTrue(frames['partial'])
        finally:
            sink.close()

    def test_zero_tick_run_and_runtime_elimination(self):
        self.add_bot('init-fail', module(init='unreachable'))
        run = self.start_run(ids=['init-fail', 'a'], seed=1).json()
        self.finish(run)
        frames = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
        self.assertEqual(len(frames['frames']), 1)
        self.assertEqual(frames['result']['reason'], 'initialization_end')
        self.add_bot('bad', module('i32.const 99'))
        run = self.start_run(key='two', ids=['bad', 'a']).json()
        final = self.finish(run)
        self.assertEqual(final['result']['ticks'], 3)
        self.assertTrue(final['verified'])

    def test_rerun_uses_original_snapshot_and_creates_separate_record(self):
        original = self.start_run(ids=['b', 'a'], seed=12).json()
        self.finish(original)
        old_bytes = Path(self.store.get('run', original['id'])['live_path']).read_bytes()
        response = self.client.post(f"/api/v1/matches/{original['id']}/rerun", headers={**HEADERS, 'Idempotency-Key': 'rerun'})
        new = response.json(); self.assertEqual(response.status_code, 202)
        self.assertNotEqual(new['id'], original['id'])
        first_inputs, next_inputs = [self.store.get('task', self.store.get('run', r['id'])['task_id'])['inputs'] for r in (original, new)]
        for key in ('entrants', 'bot_seeds', 'map_seed'):
            self.assertEqual(first_inputs[key], next_inputs[key])
        self.finish(new)
        self.assertEqual(Path(self.store.get('run', original['id'])['live_path']).read_bytes(), old_bytes)
        self.assertEqual(self.client.get('/api/v1/leaderboard').json()['valid_matches'], 2)

    def test_tampered_wasm_cannot_start_or_rerun(self):
        run = self.start_run().json(); self.finish(run)
        Path(self.store.get('bot', 'a')['wasm']).write_bytes(b'changed')
        self.assertEqual(self.start_run(key='another').status_code, 409)
        self.assertEqual(self.client.post(f"/api/v1/matches/{run['id']}/rerun", headers=HEADERS).status_code, 409)

    def test_missing_wasm_and_changed_recording_are_readable_errors(self):
        run = self.start_run().json(); self.finish(run)
        path = Path(self.store.get('run', run['id'])['live_path'])
        with path.open('ab') as stream:
            stream.write(b'changed')
        self.assertEqual(self.client.get(f"/api/v1/matches/{run['id']}/frames").status_code, 409)
        Path(self.store.get('bot', 'a')['wasm']).unlink()
        self.assertEqual(self.start_run(key='new').status_code, 409)

    def test_baselines_are_snapshots_and_do_not_generate_matches(self):
        task = prepare_baselines(self.store, self.executor)
        for identity in task['inputs']['bot_ids']:
            bot = self.store.get('bot', identity)
            self.assertTrue(Path(bot['source']).is_relative_to(self.root))
            self.assertEqual(sha_file(bot['source']), bot['source_sha256'])
        execute(self.root, task['id'])
        self.assertIsNone(prepare_baselines(self.store, self.executor))
        self.assertFalse(self.store.list('run'))

    def test_baseline_startup_reuses_legacy_ids_but_tracks_build_changes(self):
        task = prepare_baselines(self.store, self.executor)
        execute(self.root, task['id'])
        legacy_ids = []
        with self.store.connection() as db:
            for identity in task['inputs']['bot_ids']:
                row = self.store.get('bot', identity, db=db)
                row['id'] = 'legacy-' + identity
                legacy_ids.append(row['id'])
                self.store.put('bot', row, create=True, db=db)
                db.execute("DELETE FROM records WHERE kind='bot' AND id=?", (identity,))
        before = self.store.list('bot')
        self.assertIsNone(prepare_baselines(self.store, self.executor))
        self.assertEqual(self.store.list('bot'), before)
        from runner.compiler import FLAGS
        with patch('service.bots.FLAGS', [*FLAGS, '-g0']):
            changed = prepare_baselines(self.store, self.executor)
        self.assertEqual(len(changed['inputs']['bot_ids']), 3)
        self.assertFalse(set(changed['inputs']['bot_ids']) & set(legacy_ids))

    def test_bot_list_collapses_only_identical_ready_baselines(self):
        row = self.store.get('bot', 'a')
        row.update(baseline=True, source_sha256='source')
        self.store.put('bot', row)
        duplicate = {**row, 'id': 'duplicate'}
        self.store.put('bot', duplicate)
        imported = {**row, 'id': 'imported', 'baseline': False}
        self.store.put('bot', imported)
        different = {**row, 'id': 'different', 'wasm_sha256': 'other-wasm'}
        self.store.put('bot', different)
        failed = {**row, 'id': 'failed-baseline', 'status': 'failed'}
        self.store.put('bot', failed)
        before = self.store.list('bot')
        listed = self.client.get('/api/v1/bots').json()['items']
        ids = {bot['id'] for bot in listed}
        self.assertEqual(len(ids & {'a', 'duplicate'}), 1)
        self.assertTrue({'imported', 'different', 'failed-baseline', 'b'} <= ids)
        self.assertEqual(self.store.list('bot'), before)
        # Both aliases remain valid for old matches and reruns.
        run = self.start_run(ids=['a', 'duplicate']).json()
        self.assertTrue(self.finish(run)['verified'])

    def test_interrupted_run_retains_frames_and_has_no_score(self):
        run = self.start_run().json()
        task = self.store.list('task')[0]
        self.store.update('task', task['id'], lambda t: t.update(status='running'))
        self.store.update('run', run['id'], lambda r: r.update(status='running'))
        self.executor.recover_interrupted()
        self.assertEqual(self.store.get('run', run['id'])['status'], 'interrupted')
        self.assertEqual(self.client.get('/api/v1/leaderboard').json()['items'], [])
        self.assertFalse(self.client.get('/api/v1/status').json()['busy'])
        self.assertEqual(self.client.post(f"/api/v1/matches/{run['id']}/rerun", headers=HEADERS).status_code, 202)

    def test_existing_organizer_data_is_not_migrated_modified_or_counted(self):
        legacy = dict(id='old', status='running', result={'valid': True}, disclosure='sealed')
        for kind in ('session', 'submission', 'match', 'tournament', 'backup', 'job'):
            self.store.put(kind, legacy)
        self.executor.recover_interrupted()
        for kind in ('session', 'submission', 'match', 'tournament', 'backup', 'job'):
            self.assertEqual(self.store.get(kind, 'old'), legacy)
        self.assertEqual(self.client.get('/api/v1/matches').json()['total'], 0)
        self.assertEqual(self.client.get('/api/v1/leaderboard').json()['valid_matches'], 0)

    def test_removed_routes_are_not_available(self):
        for path in ('sessions', 'submissions', 'receipts', 'entrants', 'tournaments', 'jobs', 'imports', 'backups', 'exports/old'):
            self.assertEqual(self.client.get('/api/v1/' + path).status_code, 404, path)
            self.assertIn(self.client.post('/api/v1/' + path, headers=HEADERS).status_code, (404, 405), path)

    def test_local_boundary_does_not_require_a_workbench_or_cookie(self):
        self.assertEqual(self.client.post('/api/v1/matches', json={'bot_ids': ['a', 'b']}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/matches', headers={**HEADERS, 'Origin': 'https://evil.example'}, json={'bot_ids': ['a', 'b']}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/bots', headers={'Host': 'evil.example'}).status_code, 403)
        self.assertEqual(self.start_run().status_code, 202)

    def test_executor_workspace_lock_and_owned_worker_shutdown(self):
        self.executor.start()
        other = Executor(self.store)
        with self.assertRaisesRegex(RuntimeError, 'owns'):
            other.lock_workspace()
        try:
            run = self.start_run().json()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.store.get('run', run['id'])['status'] == 'pending':
                time.sleep(.05)
            self.assertEqual(self.store.get('run', run['id'])['status'], 'running')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not Path(self.store.get('run', run['id'])['live_path']).stat().st_size:
                time.sleep(.05)
            process = self.executor.process
        finally:
            self.executor.stop()
        self.assertIsNotNone(process.poll())
        self.assertEqual(self.store.get('run', run['id'])['status'], 'interrupted')
        frames = self.client.get(f"/api/v1/matches/{run['id']}/frames").json()
        self.assertFalse(frames['partial']); self.assertIsNone(frames['result'])
        other.lock_workspace(); other.stop()


class LeaderboardTests(unittest.TestCase):
    def test_scores_ties_spawn_mapping_and_failure_exclusion(self):
        bots = [dict(id=i, name=i) for i in ('a', 'b', 'idle')]
        def run(status='completed', verified=True, score=.5, swapped=False):
            return dict(status=status, verified=verified, entrants=[dict(id='b' if swapped else 'a', slot=0), dict(id='a' if swapped else 'b', slot=1)],
                        result=dict(valid=True, players=[dict(id=0, placement_score=score), dict(id=1, placement_score=1 - score)]))
        runs = [run(score=1), run(score=1, swapped=True), run(), run('failed'), run('interrupted'), run('running'), run(verified=False)]
        result = leaderboard(bots, runs)
        self.assertEqual(result['valid_matches'], 3)
        self.assertEqual([r['rank'] for r in result['items']], [1, 1])
        for row in result['items']:
            self.assertEqual((row['wins'], row['draws'], row['losses'], row['mean_score']), (1, 1, 1, .5))
        self.assertNotIn('idle', [r['id'] for r in result['items']])


if __name__ == '__main__':
    unittest.main()
