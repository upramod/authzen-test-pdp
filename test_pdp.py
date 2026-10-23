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

    def post(self, payload, content_type='application/json', request_id=None, path='/access/v1/evaluation'):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': content_type}
        if request_id:
            headers['X-Request-ID'] = request_id
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        conn.request('POST', path, data, headers)
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

    def test_put_rejected_with_405(self):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request('PUT', '/access/v1/evaluation', b'{}', {'Content-Type': 'application/json'})
        response = conn.getresponse()
        self.assertEqual(response.status, 405)
        self.assertEqual(response.getheader('Allow'), 'POST')
        response.read()
        conn.close()

    def test_idempotency(self):
        results = [json.loads(self.post(self.fixture())[2])['decision'] for _ in range(3)]
        self.assertEqual(results, [True] * 3)

    def batch(self, data):
        status, _, body = self.post(data, path='/access/v1/evaluations')
        return status, json.loads(body)

    def search(self, data, target):
        status, _, body = self.post(data, path='/access/v1/search/' + target)
        return status, json.loads(body)

    def test_batch_defaults_order_and_field_merging(self):
        data = self.fixture()
        data['action'] = {'name': 'write'}
        data['context'] = {'trace': 'fixture'}
        data['evaluations'] = [{}, {'subject': {'type': 'user', 'id': 'bob'}},
                               {'resource': {'type': 'record', 'id': 'record-2',
                                             'properties': {'status': 'archived'}}}]
        self.assertEqual(self.batch(data), (200, {'evaluations': [
            {'decision': True}, {'decision': False}, {'decision': False}]}))
        # A partial entity inherits unspecified default fields.
        data['evaluations'] = [{'subject': {'type': 'user'}}, {}]
        status, body = self.batch(data)
        self.assertEqual(status, 200)
        self.assertEqual([item['decision'] for item in body['evaluations']], [True, True])

    def test_batch_properties_and_context_override(self):
        data = self.fixture()
        data.update(action={'name': 'write'}, context={'trace': 'default'})
        data['evaluations'] = [
            {'subject': {'type': 'user', 'id': 'bob', 'properties': {'role': 'admin'}},
             'resource': {'type': 'record', 'id': 'record-2', 'properties': {'status': 'archived'}},
             'context': {}},
            {'subject': {'type': 'user', 'id': 'bob'}, 'context': None}, {}]
        status, body = self.batch(data)
        self.assertEqual(status, 200)
        self.assertEqual([item['decision'] for item in body['evaluations']], [True, False, True])

    def test_batch_read_both_records(self):
        data = {
            'subject': {'type': 'user', 'id': 'alice'},
            'action': {'name': 'read'},
            'evaluations': [
                {'resource': {'type': 'record', 'id': 'record-1'}},
                {'resource': {'type': 'record', 'id': 'record-2'}},
            ],
        }
        self.assertEqual(self.batch(data), (200, {'evaluations': [
            {'decision': True}, {'decision': True}]}))

    def test_batch_resource_type_and_properties_inherited(self):
        data = {
            'subject': {'type': 'user', 'id': 'alice'},
            'action': {'name': 'write'},
            'resource': {'type': 'record'},
            'evaluations': [
                {'resource': {'id': 'record-1', 'properties': {'status': 'active'}}},
                {'resource': {'id': 'record-2', 'properties': {'status': 'archived'}}},
            ],
        }
        self.assertEqual(self.batch(data), (200, {'evaluations': [
            {'decision': True}, {'decision': False}]}))

    def test_batch_nested_properties_merge(self):
        data = {
            'subject': {'type': 'user', 'id': 'bob',
                        'properties': {'role': 'admin', 'team': 'security'}},
            'action': {'name': 'write'},
            'resource': {'type': 'record', 'properties': {'status': 'archived'}},
            'evaluations': [
                {'resource': {'id': 'record-2', 'properties': {'label': 'restricted'}}},
            ],
        }
        self.assertEqual(self.batch(data), (200, {'evaluations': [{'decision': True}]}))

    def test_batch_deny_on_first_deny_truncates_response(self):
        data = {
            'subject': {'type': 'user', 'id': 'bob'},
            'resource': {'type': 'record', 'id': 'record-1'},
            'evaluations': [
                {'action': {'name': 'read'}},
                {'action': {'name': 'write'}},
                {'action': {'name': 'read'}},
            ],
            'options': {'evaluations_semantic': 'deny_on_first_deny'},
        }
        self.assertEqual(self.batch(data), (200, {'evaluations': [
            {'decision': True}, {'decision': False}]}))

    def test_batch_without_defaults(self):
        allow = self.fixture()
        deny = self.fixture()
        deny['subject']['id'] = 'unknown'
        self.assertEqual(self.batch({'evaluations': [allow, deny]}),
                         (200, {'evaluations': [{'decision': True}, {'decision': False}]}))

    def test_batch_single_compatibility(self):
        data = self.fixture()
        self.assertEqual(self.batch(data), (200, {'decision': True}))
        data['evaluations'] = []
        self.assertEqual(self.batch(data), (200, {'decision': True}))

    def test_batch_invalid_payloads(self):
        for data in ([], None, {'evaluations': None}, {'evaluations': {}},
                     {'evaluations': [None]}, {'evaluations': [{}], 'subject': 'alice'},
                     {'options': []}, {'options': {'evaluations_semantic': 'unknown'}}):
            with self.subTest(data=data):
                self.assertEqual(self.batch(data)[0], 400)

    def test_batch_per_item_error_does_not_stop_execution(self):
        data = {'subject': {'type': 'user', 'id': 'alice'}, 'action': {'name': 'read'},
                'options': {'evaluations_semantic': 'execute_all'},
                'evaluations': [{}, {'resource': {'type': 'record', 'id': 'record-1'}}]}
        status, body = self.batch(data)
        self.assertEqual(status, 200)
        self.assertEqual([item['decision'] for item in body['evaluations']], [False, True])

    def test_search_core_fixtures_and_ignored_target_ids(self):
        expected = {
            'subject': [{'type': 'user', 'id': 'alice'}, {'type': 'user', 'id': 'bob'}],
            'resource': [{'type': 'record', 'id': 'record-1'}, {'type': 'record', 'id': 'record-2'}],
            'action': [{'name': 'read'}, {'name': 'write'}],
        }
        for target in expected:
            data = self.fixture()
            if target == 'action':
                del data['action']
            else:
                del data[target]['id']
            with self.subTest(target=target):
                self.assertEqual(self.search(data, target), (200, {'results': expected[target]}))
                if target != 'action':
                    data[target]['id'] = 'must-be-ignored'
                data['context'] = {'trace': 'fixture'}
                data['futureField'] = True
                data['page'] = {'limit': 1, 'token': 'ignored'}
                self.assertEqual(self.search(data, target), (200, {'results': expected[target]}))

    def test_search_property_fixtures(self):
        data = {'subject': {'type': 'user'}, 'action': {'name': 'write'},
                'resource': {'type': 'record', 'id': 'record-2', 'properties': {'status': 'archived'}}}
        self.assertEqual(self.search(data, 'subject'),
                         (200, {'results': [{'type': 'user', 'id': 'bob'}]}))
        data['subject'] = {'type': 'user', 'id': 'bob', 'properties': {'role': 'admin'}}
        data['resource'] = {'type': 'record'}
        self.assertEqual(self.search(data, 'resource'),
                         (200, {'results': [{'type': 'record', 'id': 'record-2'}]}))
        data['resource'] = {'type': 'record', 'id': 'record-2', 'properties': {'status': 'archived'}}
        del data['action']
        self.assertEqual(self.search(data, 'action'), (200, {'results': [{'name': 'write'}]}))

    def test_search_unknown_entities_deny_even_with_admin_properties(self):
        for target in ('subject', 'resource', 'action'):
            for field in ('type', 'id'):
                data = self.fixture()
                key = 'resource' if target == 'subject' else 'subject'
                data[key][field] = 'unknown'
                data['subject']['properties'] = {'role': 'admin'}
                data['action']['name'] = 'write'
                data['resource']['properties'] = {'status': 'archived'}
                with self.subTest(target=target, field=field):
                    self.assertEqual(self.search(data, target), (200, {'results': []}))
        for target in ('subject', 'resource'):
            data = self.fixture()
            data[target]['type'] = 'unknown'
            self.assertEqual(self.search(data, target), (200, {'results': []}))

    def test_search_missing_fields(self):
        for target in ('subject', 'resource', 'action'):
            required = ('subject', 'resource') if target == 'action' else ('subject', 'action', 'resource')
            for key in required:
                data = self.fixture()
                del data[key]
                self.assertEqual(self.search(data, target)[0], 400)
                fields = ('name',) if key == 'action' else (('type',) if key == target else ('type', 'id'))
                for field in fields:
                    data = self.fixture()
                    del data[key][field]
                    with self.subTest(target=target, key=key, field=field):
                        self.assertEqual(self.search(data, target)[0], 400)

    def test_all_endpoints_malformed_body_and_error_request_id(self):
        paths = ['/access/v1/evaluation', '/access/v1/evaluations'] + [
            '/access/v1/search/' + target for target in ('subject', 'resource', 'action')]
        for path in paths:
            for payload in (b'{bad', b'', b'null', b'[]', b'"text"', b'\xff'):
                with self.subTest(path=path, payload=payload):
                    status, headers, _ = self.post(payload, request_id='error-123', path=path)
                    self.assertEqual(status, 400)
                    self.assertEqual(headers.get('X-Request-ID'), 'error-123')

    def test_invalid_properties_and_context_return_400(self):
        for key in ('subject', 'resource', 'action', 'context'):
            for value in (None, [], 'invalid', 42):
                data = self.fixture()
                if key == 'context':
                    data[key] = value
                else:
                    data[key]['properties'] = value
                self.assertEqual(self.post(data)[0], 400)

    def test_discovery(self):
        from pdp import PDP_IDENTIFIER, ENDPOINTS
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request('GET', '/.well-known/authzen-configuration', headers={'Host': 'untrusted.example'})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Content-Type'), 'application/json')
        body = json.loads(response.read())
        self.assertEqual(body['policy_decision_point'], PDP_IDENTIFIER)
        for key, path in ENDPOINTS.items():
            self.assertEqual(body[key], PDP_IDENTIFIER + path)
            self.assertTrue(body[key].startswith('https://'))
        conn.close()

if __name__ == '__main__': unittest.main()
