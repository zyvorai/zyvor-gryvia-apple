# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import json, tempfile, unittest
from server.core import Store, Problem


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name + "/db", clock=lambda: 1000.0)
        self.s.register("mini", dict(budgetGiB=16, runtimes=["train", "mlx"]))
        self.s.tenant("acme", 16, 1)
        self.s.model("org__base", dict(memoryGiB=4, runtime="mlx", status="ready", path="/m"))
        self.s.dataset("d1",dict(path="/d1",status="ready",node="mini"))
        self.base = "org/base"

    def tearDown(self):
        self.s.db.close(); self.tmp.cleanup()

    def body(self, **kw):
        b = dict(name="lr-sweep", base=self.base, datasetId="d1", memoryGiB=4, iters=50, grid=dict(lr=[1e-5, 5e-5], layers=[8, 16]))
        b.update(kw)
        return b

    def finish(self, val, train):
        c = self.s.claim("mini")
        self.s.logs("mini", c["id"], c["lease"], [json.dumps(dict(kind="result", adapterPath="/runs/" + c["id"][:6], finalValLoss=val, finalTrainLoss=train))])
        self.s.complete("mini", c["id"], c["lease"], True, {})
        return c["id"]

    def test_grid_expands_to_ordinary_training_jobs(self):
        sid = self.s.sweep("default", self.body())
        sw = next(x for x in self.s.snapshot()["sweeps"] if x["id"] == sid)
        self.assertEqual(len(sw["runs"]), 4)
        jobs = {j["id"]: j for j in self.s.snapshot()["jobs"]}
        combos = set()
        for r in sw["runs"]:
            j = jobs[r["job"]]
            self.assertEqual((j["spec"]["kind"], j["spec"]["modelId"], j["state"]), ("train", "org__base", "queued"))
            self.assertIn("sweep:lr-sweep", j["spec"]["labels"])
            combos.add((r["params"]["lr"], r["params"]["layers"]))
            self.assertEqual(j["spec"]["args"][j["spec"]["args"].index("--num-layers") + 1], str(r["params"]["layers"]))
        self.assertEqual(len(combos), 4)

    def test_validation(self):
        for bad in [dict(grid={}), dict(grid=dict(foo=[1])), dict(grid=dict(lr=[])), dict(grid=dict(lr=[0.1] * 5)),
                    dict(grid=dict(layers=[1.5])), dict(grid=dict(lr=[5.0])), dict(iters=0), dict(base="nope/missing"), dict(datasetId="")]:
            with self.assertRaises(Problem, msg=str(bad)):
                self.s.sweep("default", self.body(**bad))
        with self.assertRaises(Problem):   # 3 x 3 x 2 = 18 runs
            self.s.sweep("default", self.body(grid=dict(lr=[1e-5, 2e-5, 3e-5], layers=[4, 8, 16], batch=[1, 2])))
        self.assertEqual(self.s.snapshot()["sweeps"], [])
        self.assertEqual([j for j in self.s.snapshot()["jobs"] if j["state"] == "queued"], [])

    def test_failure_midway_cancels_already_submitted_runs(self):
        real, calls = self.s.submit, [0]
        def flaky(tenant, spec):
            calls[0] += 1
            if calls[0] == 3: raise Problem("boom")
            return real(tenant, spec)
        self.s.submit = flaky
        with self.assertRaises(Problem):
            self.s.sweep("default", self.body())
        self.s.submit = real
        self.assertEqual(self.s.snapshot()["sweeps"], [])
        self.assertEqual({j["state"] for j in self.s.snapshot()["jobs"]}, {"cancelled"})

    def test_ranked_by_validation_loss_with_best_marked(self):
        sid = self.s.sweep("default", self.body())
        for val, train in [(2.1, 1.9), (1.4, 1.3), (1.8, 1.6), (None, None)]:
            if val is None:
                c = self.s.claim("mini"); self.s.complete("mini", c["id"], c["lease"], False, {})
            else:
                self.finish(val, train)
        st = self.s.sweep_status(sid)
        self.assertTrue(st["complete"])
        vals = [r["valLoss"] for r in st["runs"]]
        self.assertEqual(vals, [1.4, 1.8, 2.1, None])
        self.assertEqual([r["best"] for r in st["runs"]], [True, False, False, False])
        self.assertEqual(st["best"], st["runs"][0]["job"])
        self.assertTrue(st["runs"][0]["adapter"].startswith("org__base-lora-"))

    def test_in_flight_loss_comes_from_reported_metrics(self):
        sid = self.s.sweep("default", self.body(grid=dict(lr=[1e-5])))
        c = self.s.claim("mini")
        self.s.logs("mini", c["id"], c["lease"], [json.dumps(dict(kind="metric", step=10, trainLoss=2.4, valLoss=2.6))])
        st = self.s.sweep_status(sid)
        self.assertEqual((st["runs"][0]["state"], st["runs"][0]["valLoss"], st["best"], st["complete"]), ("running", 2.6, None, False))

    def test_tenant_isolation_and_cancel(self):
        sid = self.s.sweep("acme", self.body(grid=dict(lr=[1e-5, 2e-5])))
        with self.assertRaises(Problem):
            self.s.sweep_status(sid, tenant="default")
        with self.assertRaises(Problem):
            self.s.cancel_sweep(sid, tenant="default")
        self.assertEqual(self.s.snapshot("default")["sweeps"], [])
        self.s.cancel_sweep(sid, tenant="acme")
        self.assertEqual({r["state"] for r in self.s.sweep_status(sid, tenant="acme")["runs"]}, {"cancelled"})


if __name__ == "__main__":
    unittest.main()
