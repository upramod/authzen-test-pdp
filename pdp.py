"""Local AuthZEN fixture PDP for exercising the official certification scenario.
Not a certified implementation. Run with: python pdp.py
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


def decide(request):
    subject, action, resource = (request[k] for k in ('subject', 'action', 'resource'))
    sid, name, rid = subject['id'], action['name'], resource['id']
    status = resource.get('properties', {}).get('status', 'archived' if rid == 'record-2' else 'active')
    role = subject.get('properties', {}).get('role', 'admin' if sid == 'bob' else None)
    if name == 'read' and rid == 'record-1' and sid in ('alice', 'bob'):
        return True
    if name == 'write':
        if status == 'archived':
            return role == 'admin'
        return sid == 'alice' and rid == 'record-1'
    if name == 'delete' and sid == 'alice' and rid == 'record-1':
        return action.get('properties', {}).get('soft') is True
    return False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/health':
            self.send_error(404); return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_PUT(self):
        self.send_response(405)
        self.send_header('Allow', 'POST')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        if self.path != '/access/v1/evaluation':
            self.send_error(404); return
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.send_error(400); return
        try:
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            for key in ('subject', 'action', 'resource'):
                if not isinstance(data[key], dict): raise ValueError(key)
            for key, field in (('subject', 'type'), ('subject', 'id'), ('action', 'name'), ('resource', 'type'), ('resource', 'id')):
                if not isinstance(data[key][field], str): raise ValueError(field)
            result = json.dumps({'decision': decide(data)}).encode()
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self.send_error(400); return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(result)))
        if self.headers.get('X-Request-ID'):
            self.send_header('X-Request-ID', self.headers['X-Request-ID'])
        self.end_headers(); self.wfile.write(result)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
