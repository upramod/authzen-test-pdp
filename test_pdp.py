import unittest
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pdp import Handler
from pdp import decide

class FixtureTests(unittest.TestCase):
    def check(self, sid, action, rid, expected, sp=None, ap=None, rp=None):
        req = {'subject': {'type': 'user', 'id': sid}, 'action': {'name': action}, 'resource': {'type': 'record', 'id': rid}}
        if sp is not None: req['subject']['properties'] = sp
        if ap is not None: req['action']['properties'] = ap
        if rp is not None: req['resource']['properties'] = rp
        self.assertEqual(decide(req), expected)

    def test_required_eight(self):
        self.check('alice', 'read', 'record-1', True)
        self.check('alice', 'write', 'record-1', True)
        self.check('bob', 'read', 'record-1', True)
        self.check('bob', 'write', 'record-1', False)
        self.check('alice', 'write', 'record-2', False, rp={'status': 'archived'})
        self.check('bob', 'write', 'record-2', True, sp={'role':'admin'}, rp={'status':'archived'})
        self.check('alice', 'delete', 'record-1', True, ap={'soft':True})
        self.check('alice', 'delete', 'record-1', False, ap={'soft':False})


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def post(self, payload, content_type='application/json', request_id=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': content_type}
        if request_id:
            headers['X-Request-ID'] = request_id
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        conn.request('POST', '/access/v1/evaluation', data, headers)
        response = conn.getresponse()
        status, headers, body = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return status, headers, body

    def fixture(self):
        return {'subject': {'type': 'user', 'id': 'alice'}, 'action': {'name': 'read'}, 'resource': {'type': 'record', 'id': 'record-1'}}

    def test_valid_request_context_and_unknown_fields(self):
        data = self.fixture()
        data['context'] = {'ip': '127.0.0.1'}
        data['futureField'] = {'nested': True}
        status, headers, body = self.post(data, request_id='req-123')
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('X-Request-ID'), 'req-123')
        self.assertEqual(json.loads(body), {'decision': True})

    def test_missing_required_subfields(self):
        for key, field in [('subject', 'type'), ('subject', 'id'), ('action', 'name'), ('resource', 'type'), ('resource', 'id')]:
            with self.subTest(key=key, field=field):
                data = self.fixture()
                del data[key][field]
                self.assertEqual(self.post(data)[0], 400)

    def test_missing_top_level_fields(self):
        for key in ('subject', 'action', 'resource'):
            with self.subTest(key=key):
                data = self.fixture()
                del data[key]
                self.assertEqual(self.post(data)[0], 400)

    def test_invalid_requests(self):
        self.assertEqual(self.post(b'{bad json')[0], 400)
        self.assertEqual(self.post(b'')[0], 400)
        self.assertEqual(self.post(self.fixture(), 'text/plain')[0], 400)
        data = self.fixture()
        data['subject'] = 'alice'
        self.assertEqual(self.post(data)[0], 400)
        data = self.fixture()
        data['action']['name'] = 123
        self.assertEqual(self.post(data)[0], 400)

    def test_idempotency(self):
        results = [json.loads(self.post(self.fixture())[2])['decision'] for _ in range(3)]
        self.assertEqual(results, [True] * 3)

if __name__ == '__main__': unittest.main()
