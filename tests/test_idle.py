# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import json, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from server.app import make_server
from server.core import Store
from server.inference import Gateway
from tests.test_inference import Worker

HOUR = 3600

class IdleEvictionTests(unittest.TestCase):
    """Deploys through the serve job's endpoint log and sends traffic through the real Gateway,
    so activity is recorded exactly as production records it."""
    def setUp(self):
        self.now = 1_000_000.0
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name + '/db', clock=lambda: self.now)
        self.store.tenant('team', 16)
        self.store.register('mini', dict(budgetGiB=16, slots=4, runtimes=['serve']))
        self.worker = ThreadingHTTPServer(('127.0.0.1', 0), Worker)
        self.thread = threading.Thread(target=self.worker.serve_forever, daemon=True); self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.worker.server_port)
        self.gateway = Gateway([self.origin]); self.leases = {}

    def tearDown(self):
        self.worker.shutdown(); self.worker.server_close(); self.thread.join()
        self.store.db.close(); self.temp.cleanup()

    def deploy(self, mid):
        jid = self.store.submit('team', dict(kind='serve', runtime='serve', memoryGiB=4, modelId=mid, mode='shared', timeoutSeconds=86400))
        claim = self.store.claim('mini')
        self.assertEqual(claim['id'], jid)
        self.leases[jid] = claim['lease']
        self.store.log('mini', jid, claim['lease'], json.dumps(dict(kind='endpoint', url=self.origin)))
        return jid

    def advance(self, seconds):
        # Behave like a live agent: heartbeat and renew leases well inside their 20 s expiry.
        end = self.now + seconds
        while self.now < end:
            self.now = min(end, self.now + 15)
            self.store.register('mini', dict(budgetGiB=16, slots=4, runtimes=['serve']))
            for jid, lease in self.leases.items():
                if self.state(jid) in ('running', 'cancelling'): self.store.renew('mini', jid, lease)

    def chat(self, mid, stream=False):
        body = {'model': mid, 'messages': [{'role': 'user', 'content': 'hi'}]}
        if stream: list(self.gateway.stream(self.store, 'team', {**body, 'stream': True}))
        else: self.gateway.chat(self.store, 'team', body)

    def state(self, jid):
        return self.store.db.execute('SELECT state FROM jobs WHERE id=?', (jid,)).fetchone()['state']

    def test_fresh_deploy_of_old_model_is_not_idle(self):
        self.store.model('m', dict(memoryGiB=4))
        self.now += 2 * 86400            # registered long ago, deployed now
        self.store.register('mini', dict(budgetGiB=16, slots=4, runtimes=['serve']))
        self.deploy('m')
        self.assertEqual(self.store.idle_deployments(HOUR), [])

    def test_gateway_traffic_keeps_model_alive(self):
        self.store.model('m', dict(memoryGiB=4)); self.deploy('m')
        self.advance(50 * 60); self.chat('m')
        self.advance(50 * 60); self.chat('m', stream=True)
        self.advance(50 * 60)              # 150 min after deploy, 50 min after the last request
        self.assertEqual(self.store.idle_deployments(HOUR), [])
        self.assertEqual(self.store.evict_idle(HOUR), [])

    def test_evicts_only_the_idle_model_and_is_repeatable(self):
        self.store.model('busy', dict(memoryGiB=4)); self.store.model('quiet', dict(memoryGiB=4))
        busy = self.deploy('busy'); quiet = self.deploy('quiet')
        self.advance(2 * HOUR); self.chat('busy')
        idle = self.store.idle_deployments(HOUR)
        self.assertEqual([i['id'] for i in idle], ['quiet'])
        self.assertGreater(idle[0]['idle'], HOUR)
        self.assertEqual(self.store.evict_idle(HOUR, 'nightly'), [quiet])
        self.assertEqual((self.state(quiet), self.state(busy)), ('cancelling', 'running'))
        self.assertEqual(self.store.evict_idle(HOUR), [])
        events = [tuple(r) for r in self.store.db.execute("SELECT subject, detail FROM events WHERE kind='model.evict_idle'")]
        self.assertEqual(events, [('quiet', 'nightly ' + quiet)])

    def test_capacity_summary_reports_reservations_not_utilisation(self):
        self.store.model('m', dict(memoryGiB=4)); self.deploy('m')
        s = self.store.capacity_summary()
        self.assertEqual((s['online'], s['budgetGiB'], s['reservedGiB'], s['freeGiB'], s['running']), (1, 16, 4, 12, 1))
        self.assertEqual(s['reservedPct'], 25.0)
        self.assertNotIn('utilisationPct', s)


class IdleEvictionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name + '/db')
        self.server = make_server(self.store, {'a' * 32: dict(role='admin'), 't' * 32: dict(role='tenant', tenant='team')}, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.store.db.close(); self.temp.cleanup()

    def call(self, path, body=None, token='a' * 32):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=5) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e: return e.code, json.loads(e.read())

    def test_valid_requests(self):
        self.assertEqual(self.call('/api/models/idle?seconds=60'), (200, []))
        self.assertEqual(self.call('/api/models/evict-idle', dict(seconds=60, reason='nightly')), (200, dict(cancelled=[], count=0)))
        self.assertEqual(self.call('/api/capacity')[0], 200)

    def test_rejects_bad_input_with_400(self):
        for query in ('abc', 'nan', 'inf', '-1', str(31 * 86400)):
            self.assertEqual(self.call('/api/models/idle?seconds=' + query)[0], 400, query)
        for body in (dict(seconds='60'), dict(seconds=-1), dict(seconds=True), dict(seconds=60, reason=''),
                     dict(seconds=60, reason='x' * 201), dict(seconds=60, reason=7)):
            self.assertEqual(self.call('/api/models/evict-idle', body)[0], 400, body)

    def test_admin_only(self):
        for path, body in (('/api/models/idle', None), ('/api/capacity', None), ('/api/models/evict-idle', dict(seconds=60))):
            self.assertEqual(self.call(path, body, token='t' * 32)[0], 403, path)

if __name__ == '__main__':
    unittest.main()
