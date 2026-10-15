# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import json, time, tempfile, unittest
from server.core import Store

class IdleEvictionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name + '/db', clock=lambda: self.now)
        self.now = 1_000_000.0
        self.store.tenant('team', 16)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def _deployed_model(self, mid='m1', age_seconds=7200, endpoints=None):
        # model() forces updated=clock(); so we insert then age the clock, or patch after
        body = dict(memoryGiB=4, runtime='mlx', status='deployed',
                    endpoints=endpoints or ['http://127.0.0.1:8080'],
                    deployJob='j-serve')
        self.store.model(mid, body)
        # age the stored updated timestamp
        row = self.store.db.execute('SELECT body FROM models WHERE id=?', (mid,)).fetchone()
        m = json.loads(row['body'])
        m['updated'] = self.now - age_seconds
        self.store.db.execute('UPDATE models SET body=? WHERE id=?', (json.dumps(m), mid))
        return mid

    def test_idle_detects_old_deploy(self):
        self._deployed_model()
        idle = self.store.idle_deployments(3600)
        self.assertEqual(len(idle), 1)
        self.assertEqual(idle[0]['id'], 'm1')
        self.assertGreater(idle[0]['idle'], 3600)

    def test_recent_inference_keeps_alive(self):
        self._deployed_model()
        self.store.event('inference.completed', 'm1', 'ok')
        idle = self.store.idle_deployments(3600)
        self.assertEqual(idle, [])

    def test_evict_cancels_serve_job(self):
        self._deployed_model()
        # create a running serve job
        jid = self.store.submit('team', dict(kind='serve', runtime='mlx', memoryGiB=4, modelId='m1', priority=1))
        # force it into running by claiming (simplified: just set state)
        self.store.db.execute("UPDATE jobs SET state='running', node='mini' WHERE id=?", (jid,))
        cancelled = self.store.evict_idle(3600)
        self.assertIn(jid, cancelled)
        row = self.store.db.execute('SELECT state FROM jobs WHERE id=?', (jid,)).fetchone()
        self.assertEqual(row['state'], 'cancelling')

    def test_capacity_summary(self):
        # register a node
        self.store.register('mini', dict(budgetGiB=16, slots=1, runtimes=['mlx']))
        s = self.store.capacity_summary()
        self.assertEqual(s['online'], 1)
        self.assertEqual(s['budgetGiB'], 16)
        self.assertEqual(s['freeGiB'], 16)

if __name__ == '__main__':
    unittest.main()
