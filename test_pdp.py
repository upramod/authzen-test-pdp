import unittest
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

if __name__ == '__main__': unittest.main()
