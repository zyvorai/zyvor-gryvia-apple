# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import json, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from server.core import Store, Problem
from server.inference import Gateway
from tests.test_inference import Worker

NODES = ('mini', 'book')

class ReplicaTests(unittest.TestCase):
    """Two serve jobs for one model on two Macs, deployed through the real endpoint log path."""
    def setUp(self):
        self.now = 1_000_000.0
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name + '/db', clock=lambda: self.now)
        self.store.tenant('team', 32)
        for n in NODES: self.store.register(n, dict(budgetGiB=16, slots=4, runtimes=['serve']))
        self.workers = {}
        for n in NODES:
            w = ThreadingHTTPServer(('127.0.0.1', 0), Worker)
            threading.Thread(target=w.serve_forever, daemon=True).start()
            self.workers[n] = w
        self.origins = {n: 'http://127.0.0.1:%d' % w.server_port for n, w in self.workers.items()}
        self.gateway = Gateway(list(self.origins.values()), max_inflight=8)
        self.store.model('m', dict(memoryGiB=4, path='/models/m.gguf')); self.jobs = {}; self.leases = {}

    def tearDown(self):
        for w in self.workers.values():
            try: w.shutdown()
            except Exception: pass
            w.server_close()
        self.store.db.close(); self.temp.cleanup()

    def deploy(self, node):
        jid = self.store.submit('team', dict(kind='serve', runtime='serve', memoryGiB=4, modelId='m', mode='shared', timeoutSeconds=86400, node=node))
        claim = self.store.claim(node); self.assertEqual(claim['id'], jid)
        self.jobs[node] = jid; self.leases[node] = claim['lease']
        self.store.log(node, jid, claim['lease'], json.dumps(dict(kind='endpoint', url=self.origins[node])))
        return jid

    def model(self):
        return next(m for m in self.store.snapshot()['models'] if m['id'] == 'm')

    def chat(self):
        return self.gateway.chat(self.store, 'team', {'model': 'm', 'messages': [{'role': 'user', 'content': 'hi'}]})

    def seen(self, node):
        return getattr(self.workers[node], 'seen', None)

    def test_two_deployments_are_two_replicas(self):
        self.deploy('mini'); self.deploy('book')
        m = self.model()
        self.assertEqual(m['status'], 'deployed')
        self.assertEqual({r['node'] for r in m['replicas']}, set(NODES))
        self.assertEqual(sorted(m['endpoints']), sorted(self.origins.values()))

    def test_repeated_endpoint_line_does_not_duplicate(self):
        jid = self.deploy('mini')
        self.store.log('mini', jid, self.leases['mini'], json.dumps(dict(kind='endpoint', url=self.origins['mini'])))
        self.assertEqual(len(self.model()['replicas']), 1)

    def test_traffic_reaches_both_replicas_when_one_is_busy(self):
        self.deploy('mini'); self.deploy('book')
        self.gateway.active[self.origins['mini']] = 1      # a request in flight on mini
        self.chat()
        self.assertIsNotNone(self.seen('book')); self.assertIsNone(self.seen('mini'))
        self.gateway.active[self.origins['mini']] = 0; self.gateway.active[self.origins['book']] = 1
        self.chat()
        self.assertIsNotNone(self.seen('mini'))

    def test_failover_when_a_replica_is_down(self):
        self.deploy('mini'); self.deploy('book')
        self.workers['mini'].shutdown(); self.workers['mini'].server_close()
        self.gateway.active[self.origins['book']] = 1      # prefer the dead one first
        self.assertIn('choices', self.chat())
        self.assertIsNotNone(self.seen('book'))
        self.assertEqual(self.gateway.active[self.origins['mini']], 0)   # slots released
        self.assertEqual(self.gateway.calls.get('team', 0), 0)

    def test_failover_stream_before_first_byte(self):
        self.deploy('mini'); self.deploy('book')
        self.workers['mini'].shutdown(); self.workers['mini'].server_close()
        self.gateway.active[self.origins['book']] = 1
        stream = self.gateway.stream(self.store, 'team', {'model': 'm', 'stream': True, 'messages': [{'role': 'user', 'content': 'hi'}]})
        data = b''.join(stream); stream.close()
        self.assertIn(b'Hello', data)
        self.assertEqual(self.gateway.calls.get('team', 0), 0)

    def test_all_replicas_down_reports_the_replica_failure(self):
        self.deploy('mini'); self.deploy('book')
        for w in self.workers.values(): w.shutdown(); w.server_close()
        with self.assertRaises(Problem) as ctx: self.chat()
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(self.gateway.calls.get('team', 0), 0)

    def test_single_replica_failure_is_not_retried_on_itself(self):
        self.deploy('mini')
        self.workers['mini'].shutdown(); self.workers['mini'].server_close()
        with self.assertRaises(Problem) as ctx: self.chat()
        self.assertEqual(ctx.exception.status, 502)

    def test_one_replica_ending_keeps_the_model_deployed(self):
        self.deploy('mini'); self.deploy('book')
        self.store.complete('mini', self.jobs['mini'], self.leases['mini'], False, {})
        m = self.model()
        self.assertEqual(m['status'], 'deployed')
        self.assertEqual([r['node'] for r in m['replicas']], ['book'])
        self.assertEqual(m['deployJob'], self.jobs['book']); self.assertEqual(m['endpoints'], [self.origins['book']])
        self.assertIn('choices', self.chat())
        self.store.complete('book', self.jobs['book'], self.leases['book'], False, {})
        m = self.model()
        self.assertEqual(m['endpoints'], []); self.assertNotIn('replicas', m); self.assertNotEqual(m['status'], 'deployed')

    def test_failed_unrelated_serve_job_does_not_touch_replicas(self):
        self.deploy('mini')
        jid = self.store.submit('team', dict(kind='serve', runtime='serve', memoryGiB=4, modelId='m', mode='shared', timeoutSeconds=60, node='book'))
        claim = self.store.claim('book')
        self.store.complete('book', jid, claim['lease'], False, {})     # died before announcing an endpoint
        self.assertEqual(self.model()['status'], 'deployed'); self.assertEqual(len(self.model()['replicas']), 1)

    def test_evict_idle_cancels_every_replica(self):
        a = self.deploy('mini'); b = self.deploy('book')
        end = self.now + 7200
        while self.now < end:      # behave like live agents: heartbeat and renew inside the lease expiry
            self.now += 15
            for n in NODES:
                self.store.register(n, dict(budgetGiB=16, slots=4, runtimes=['serve']))
                self.store.renew(n, self.jobs[n], self.leases[n])
        self.assertEqual(sorted(self.store.evict_idle(3600)), sorted([a, b]))

    def test_replica_count_is_bounded(self):
        from server.core import MAX_REPLICAS
        self.store.register('mini', dict(budgetGiB=64, slots=20, runtimes=['serve']))
        for i in range(MAX_REPLICAS + 2):
            jid = self.store.submit('team', dict(kind='serve', runtime='serve', memoryGiB=1, modelId='m', mode='shared', timeoutSeconds=600, node='mini'))
            claim = self.store.claim('mini'); self.assertEqual(claim['id'], jid)
            self.store.log('mini', jid, claim['lease'], json.dumps(dict(kind='endpoint', url='http://127.0.0.1:%d' % (9000 + i))))
        reps = self.model()['replicas']
        self.assertEqual(len(reps), MAX_REPLICAS)
        self.assertEqual(reps[-1]['url'], 'http://127.0.0.1:%d' % (9000 + MAX_REPLICAS + 1))

if __name__ == '__main__': unittest.main()
