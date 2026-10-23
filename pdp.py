"""Local AuthZEN fixture PDP for exercising the official certification scenario.
Not a certified implementation. Run with: python pdp.py
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os


PDP_IDENTIFIER = os.environ.get(
    'PDP_IDENTIFIER',
    'https://authzen-test-pdp.calmbeach-7657ba97.westus2.azurecontainerapps.io',
)
ENDPOINTS = {
    'access_evaluation_endpoint': '/access/v1/evaluation',
    'access_evaluations_endpoint': '/access/v1/evaluations',
    'search_subject_endpoint': '/access/v1/search/subject',
    'search_resource_endpoint': '/access/v1/search/resource',
    'search_action_endpoint': '/access/v1/search/action',
}


def validate(request, target=None):
    if not isinstance(request, dict):
        raise ValueError('Request must be an object')
    for key in ('subject', 'action', 'resource'):
        if key == target == 'action':
            continue
        entity = request.get(key)
        if not isinstance(entity, dict):
            raise ValueError(key + ' must be an object')
        fields = ('name',) if key == 'action' else ('type', 'id')
        for field in fields:
            if field == 'id' and key == target:
                continue
            if not isinstance(entity.get(field), str):
                raise ValueError(key + '.' + field + ' must be a string')
        if 'properties' in entity and not isinstance(entity['properties'], dict):
            raise ValueError(key + '.properties must be an object')
    if 'context' in request and not isinstance(request['context'], dict):
        raise ValueError('context must be an object')


def evaluate(request):
    validate(request)
    return {'decision': decide(request)}


def evaluate_batch(request):
    if not isinstance(request, dict):
        raise ValueError('Request must be an object')
    items = request.get('evaluations', [])
    if not isinstance(items, list):
        raise ValueError('evaluations must be an array')
    options = request.get('options', {})
    if not isinstance(options, dict):
        raise ValueError('options must be an object')
    if options.get('evaluations_semantic', 'execute_all') != 'execute_all':
        raise ValueError('Only execute_all is supported')
    if not items:
        return evaluate(request)
    for key in ('subject', 'action', 'resource', 'context'):
        if key in request and not isinstance(request[key], dict):
            raise ValueError(key + ' must be an object')
    results = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Each evaluation must be an object')
        merged = {}
        for key in ('subject', 'action', 'resource', 'context'):
            if key not in item and key not in request:
                continue
            default = request.get(key, {})
            override = item.get(key, {})
            if isinstance(default, dict) and isinstance(override, dict):
                entity = {**default, **override}
                if isinstance(default.get('properties'), dict) and isinstance(override.get('properties'), dict):
                    entity['properties'] = {**default['properties'], **override['properties']}
                merged[key] = entity
            else:
                merged[key] = override if key in item else default
        try:
            results.append(evaluate(merged))
        except ValueError:
            results.append({'decision': False, 'context': {'error': 'invalid_evaluation'}})
    return {'evaluations': results}


def search(request, target):
    validate(request, target)
    candidates = {
        'subject': [{'type': 'user', 'id': sid} for sid in ('alice', 'bob')],
        'resource': [{'type': 'record', 'id': rid} for rid in ('record-1', 'record-2')],
        'action': [{'name': name} for name in ('read', 'write', 'delete')],
    }[target]
    results = []
    for candidate in candidates:
        if target != 'action' and candidate['type'] != request[target]['type']:
            continue
        entity = dict(candidate)
        if target != 'action' and 'properties' in request[target]:
            entity['properties'] = request[target]['properties']
        if decide({**request, target: entity}):
            results.append(candidate)
    # The fixture is small. Pagination is deliberately unsupported: return all
    # matches and accept (ignore) page parameters, as permitted by section 8.2.
    return {'results': results}


def decide(request):
    subject, action, resource = (request[k] for k in ('subject', 'action', 'resource'))
    sid, name, rid = subject['id'], action['name'], resource['id']
    if (subject['type'] != 'user' or resource['type'] != 'record'
            or sid not in ('alice', 'bob') or rid not in ('record-1', 'record-2')):
        return False
    status = resource.get('properties', {}).get('status', 'archived' if rid == 'record-2' else 'active')
    role = subject.get('properties', {}).get('role', 'admin' if sid == 'bob' else None)
    if name == 'read' and sid in ('alice', 'bob'):
        return True
    if name == 'write':
        if status == 'archived':
            return role == 'admin'
        return sid == 'alice' and rid == 'record-1'
    if name == 'delete' and sid == 'alice' and rid == 'record-1':
        return action.get('properties', {}).get('soft') is True
    return False


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        result = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(result)))
        if self.headers.get('X-Request-ID'):
            self.send_header('X-Request-ID', self.headers['X-Request-ID'])
        self.end_headers()
        self.wfile.write(result)

    def do_GET(self):
        if self.path == '/health':
            self.respond(200, {'status': 'ok'})
        elif self.path == '/.well-known/authzen-configuration':
            self.respond(200, {'policy_decision_point': PDP_IDENTIFIER,
                              **{key: PDP_IDENTIFIER + path for key, path in ENDPOINTS.items()}})
        else:
            self.respond(405 if self.path in ENDPOINTS.values() else 404, {'error': 'unsupported_path_or_method'})

    def do_PUT(self):
        self.send_response(405)
        self.send_header('Allow', 'POST')
        self.send_header('Content-Length', '0')
        if self.headers.get('X-Request-ID'):
            self.send_header('X-Request-ID', self.headers['X-Request-ID'])
        self.end_headers()

    def do_POST(self):
        if self.path not in ENDPOINTS.values():
            self.respond(404, {'error': 'unknown_endpoint'}); return
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            self.respond(400, {'error': 'invalid_content_type'}); return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length < 1 or length > 1048576:
                raise ValueError('Invalid body size')
            data = json.loads(self.rfile.read(length))
            if self.path == ENDPOINTS['access_evaluation_endpoint']:
                result = evaluate(data)
            elif self.path == ENDPOINTS['access_evaluations_endpoint']:
                result = evaluate_batch(data)
            else:
                result = search(data, self.path.rsplit('/', 1)[1])
        except (ValueError, KeyError, TypeError):
            self.respond(400, {'error': 'invalid_request'}); return
        self.respond(200, result)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
