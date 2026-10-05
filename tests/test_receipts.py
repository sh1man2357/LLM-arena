"""Owner lifecycle views must not create programs or disclose private receipts."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from service.app import create_app
from service.jobs import Queue
from service.submissions import create_session, submit


class ReceiptTests(unittest.TestCase):
    def test_private_access_and_safe_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            store = app.state.store
            session = create_session(store, 'Private name', 'Model')
            submission = submit(store, session['id'], 'private-source-marker')
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/v1/admin/status').json(), {'owner': False})
                for path in ('/api/v1/receipts', f"/api/v1/receipts/{session['id']}", '/api/v1/receipts/unknown'):
                    denied = client.get(path)
                    self.assertEqual(denied.status_code, 403)
                    self.assertNotIn('Private name', denied.text)
                client.post('/api/v1/admin/unlock', headers={'x-arena-local': '1'})
                self.assertEqual(client.get('/api/v1/admin/status').json(), {'owner': True})
                actual = client.get(f"/api/v1/receipts/{session['id']}").json()
                self.assertEqual(actual['submission']['source_sha256'], submission['source_sha256'])
                self.assertEqual(actual['status'], 'submitted')
                for secret in ('private-source-marker', folder.replace('\\', '\\\\'), 'request_hash', '"key"'):
                    self.assertNotIn(secret, json.dumps(actual))
                self.assertEqual(client.get('/api/v1/receipts/unknown').status_code, 404)
                self.assertEqual(client.get('/api/v1/entrants').json()['items'], [])
                source_path = f"/api/v1/submissions/{submission['id']}/source"
                self.assertEqual(client.get(source_path).text, 'private-source-marker')
                Path(submission['source']).write_text('modified on disk',encoding='utf-8')
                self.assertEqual(client.get(source_path).status_code,409)
                client.cookies.clear()
                self.assertEqual(client.get(f"/api/v1/submissions/{submission['id']}/source").status_code, 403)

    def test_deadline_missing_and_late_are_derived_without_mutating_records(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            store = app.state.store
            start = datetime.now(timezone.utc) - timedelta(minutes=70)
            missing = create_session(store, 'Missing', 'test', start.isoformat(), 'external_record')
            late = create_session(store, 'Late', 'test', start.isoformat(), 'external_record')
            submit(store, late['id'], 'late', received_at=(start+timedelta(minutes=60,microseconds=1)).isoformat())
            with TestClient(app) as client:
                client.post('/api/v1/admin/unlock', headers={'x-arena-local':'1'})
                records = {r['id']:r for r in client.get('/api/v1/receipts').json()['items']}
                self.assertEqual(records[missing['id']]['status'], 'missing')
                self.assertEqual(records[late['id']]['status'], 'late')
                self.assertEqual(store.get('session', missing['id'])['status'], 'open')
                self.assertEqual(len(store.list('session')), 2)
                self.assertEqual(store.list('entrant'), [])

    def test_queue_running_failure_and_retry_keep_the_frozen_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            store = app.state.store
            session = create_session(store, 'Lifecycle', 'test')
            frozen = submit(store, session['id'], 'frozen')
            job = Queue(store).create('compile', {'submission_id':frozen['id']})
            with TestClient(app) as client:
                client.post('/api/v1/admin/unlock', headers={'x-arena-local':'1'})
                url = f"/api/v1/receipts/{session['id']}"
                self.assertEqual(client.get(url).json()['status'], 'queued')
                store.update('job',job['id'],lambda r:r.update(status='running'))
                self.assertEqual(client.get(url).json()['status'], 'compiling')
                store.update('job',job['id'],lambda r:r.update(status='failed',diagnostic='integrity failure'))
                self.assertEqual(client.get(url).json()['status'], 'failed')
                store.update('submission',frozen['id'],lambda r:r.update(status='qualification_failed',diagnostic='actual compiler error'))
                failed = client.get(url).json()
                self.assertEqual(failed['status'], 'qualification_failed')
                self.assertEqual(failed['submission']['diagnostic'], 'actual compiler error')
                Queue(store).resume(job['id'])
                retried = client.get(url).json()
                self.assertEqual(retried['status'], 'queued')
                self.assertEqual(retried['submission']['source_sha256'],frozen['source_sha256'])
                self.assertEqual(store.list('entrant'), [])


if __name__ == '__main__':
    unittest.main()
