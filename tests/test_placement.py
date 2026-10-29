# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import tempfile, unittest
from server.core import Store, Problem

class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.now=100.; self.store=Store(self.temp.name+'/db',lambda:self.now)
        self.node('mini',cores=10); self.node('studio',cores=60)
    def tearDown(self): self.store.db.close(); self.temp.cleanup()
    def node(self,name,cores=None,budget=16,**kw):
        body=dict(budgetGiB=budget,slots=1,runtimes=['demo','mlx'],**kw)
        if cores: body['gpuCores']=cores
        self.store.register(name,body)
    def sub(self,**kw):
        self.now+=0.001; return self.store.submit('default',{**dict(runtime='mlx',kind='train',memoryGiB=4),**kw})
    def reason(self,job): return next(j for j in self.store.snapshot()['jobs'] if j['id']==job)['reason']
    def test_validation(self):
        for bad in (dict(avoidNodes='mini'),dict(avoidNodes=['a']*9),dict(minGpuCores=0),dict(minGpuCores=True),dict(minGpuCores=1.5),dict(minBudgetGiB=-1),dict(node='mini',avoidNodes=['mini'])):
            with self.assertRaises(Problem,msg=str(bad)): self.sub(**bad)
    def test_avoid_nodes(self):
        j=self.sub(avoidNodes=['mini'],kind='download'); self.assertIsNone(self.store.claim('mini')); self.assertIn('avoided',self.reason(j))
        self.assertEqual(self.store.claim('studio')['id'],j)
    def test_min_gpu_cores_and_budget(self):
        j=self.sub(minGpuCores=40,kind='download'); self.assertIsNone(self.store.claim('mini')); self.assertIn('40 GPU cores',self.reason(j)); self.assertEqual(self.store.claim('studio')['id'],j)
        self.node('small',cores=60,budget=8); k=self.sub(minBudgetGiB=12,kind='download'); self.assertIsNone(self.store.claim('small')); self.assertIn('12 GiB',self.reason(k))
    def test_slower_mac_yields_for_a_bounded_number_of_polls(self):
        j=self.sub()
        for _ in range(Store.DEFER_POLLS):
            self.assertIsNone(self.store.claim('mini')); self.assertIn('faster Mac (studio',self.reason(j))
        self.assertEqual(self.store.claim('mini')['id'],j)     # never starves
    def test_faster_mac_claims_immediately(self):
        j=self.sub(); self.assertEqual(self.store.claim('studio')['id'],j)
    def test_no_yield_when_faster_mac_cannot_run_it(self):
        self.store.drain('studio',True); j=self.sub(); self.assertEqual(self.store.claim('mini')['id'],j)
    def test_no_yield_when_faster_mac_is_busy(self):
        busy=self.sub(); self.assertEqual(self.store.claim('studio')['id'],busy)   # studio's only slot is taken
        j=self.sub(); self.assertEqual(self.store.claim('mini')['id'],j)
    def test_no_yield_for_non_gpu_kinds(self):
        j=self.sub(kind='download'); self.assertEqual(self.store.claim('mini')['id'],j)
    def test_pinned_job_does_not_yield(self):
        j=self.sub(node='mini'); self.assertEqual(self.store.claim('mini')['id'],j)
    def test_similar_macs_do_not_yield(self):
        self.node('studio',cores=12); j=self.sub(); self.assertEqual(self.store.claim('mini')['id'],j)
    def test_unknown_cores_do_not_yield(self):
        self.node('mini'); j=self.sub(); self.assertEqual(self.store.claim('mini')['id'],j)
if __name__=='__main__': unittest.main()
