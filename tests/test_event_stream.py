"""New viewers start at current state; reconnect cursors retain ordered catch-up."""
import json
import tempfile
import unittest

from starlette.requests import Request
from service.app import create_app, APIError


class EventStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_stream_skips_old_notices_but_receives_next_event(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            store = app.state.store
            for i in range(10):
                store.emit('old', 'job', {'progress': i})
            endpoint = next(r.endpoint for r in app.routes if getattr(r, 'path', '') == '/api/v1/events')
            response = await endpoint(self.request())
            stream = response.body_iterator
            try:
                self.assertEqual(await anext(stream), ': keepalive\n\n')
                identity = store.emit('current', 'job', {'status': 'running', 'private_path': 'must-not-publish'})
                notice = await anext(stream)
                self.assertEqual(self.event(notice)['event_id'], identity)
                self.assertEqual(self.event(notice)['resource_id'], 'current')
                self.assertNotIn('private_path', notice)
            finally:
                await stream.aclose()

    async def test_explicit_zero_and_last_event_id_preserve_catch_up(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            store = app.state.store
            first = store.emit('one', 'job', {'status': 'running'})
            second = store.emit('two', 'frame', {'seq': 2, 'attempt_id': 'current'})
            endpoint = next(r.endpoint for r in app.routes if getattr(r, 'path', '') == '/api/v1/events')
            for after, header, expected in [(0, None, [first, second]), (None, str(first), [second]), (0, str(first), [second])]:
                response = await endpoint(self.request(header), after=after)
                stream = response.body_iterator
                try:
                    actual = [self.event(await anext(stream))['event_id'] for _ in expected]
                    self.assertEqual(actual, expected)
                finally:
                    await stream.aclose()
            with self.assertRaises(APIError) as invalid:
                await endpoint(self.request('invalid'))
            self.assertEqual(invalid.exception.status, 422)

    @staticmethod
    def event(chunk):
        return json.loads(next(line[6:] for line in chunk.splitlines() if line.startswith('data: ')))

    @staticmethod
    def request(last=None):
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        return Request({'type': 'http', 'method': 'GET', 'path': '/api/v1/events',
                        'headers': [] if last is None else [(b'last-event-id', last.encode())]}, receive)


if __name__ == '__main__':
    unittest.main()
