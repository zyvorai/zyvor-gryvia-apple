# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import json, threading, tempfile, unittest, urllib.request, urllib.error
from server.app import make_server, FailureLimiter
from server.core import Store, Problem

class Clock:
    def __init__(self): self.t=1000.0
    def __call__(self): return self.t

class EnrollStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.clock=Clock(); self.store=Store(self.temp.name+'/db',clock=self.clock)
    def tearDown(self): self.store.db.close(); self.temp.cleanup()
    def test_code_is_single_use_and_hashed(self):
        j=self.store.create_join(); token=self.store.enroll(j['code'],'studio')
        self.assertEqual(self.store.agent_actor(token),{'role':'agent','node':'studio'})
        with self.assertRaises(Problem) as c: self.store.enroll(j['code'],'studio2')
        self.assertEqual(c.exception.status,403)
        dump=' '.join(str(tuple(r)) for t in ('join_codes','agent_tokens') for r in self.store.db.execute('SELECT * FROM '+t))
        self.assertNotIn(j['code'],dump); self.assertNotIn(token,dump)
    def test_expiry(self):
        j=self.store.create_join(ttl=60); self.clock.t+=61
        with self.assertRaises(Problem): self.store.enroll(j['code'],'studio')
    def test_bound_code_only_enrols_its_node(self):
        j=self.store.create_join('mini-01')
        with self.assertRaises(Problem): self.store.enroll(j['code'],'other')
        self.assertTrue(self.store.enroll(j['code'].lower(),'mini-01'))
    def test_existing_node_needs_a_bound_code_and_replaces_token(self):
        old=self.store.enroll(self.store.create_join()['code'],'mini')
        with self.assertRaises(Problem) as c: self.store.enroll(self.store.create_join()['code'],'mini')
        self.assertEqual(c.exception.status,409)
        new=self.store.enroll(self.store.create_join('mini')['code'],'mini')
        self.assertIsNone(self.store.agent_actor(old)); self.assertIsNotNone(self.store.agent_actor(new))
    def test_revoke(self):
        j=self.store.create_join(); self.store.revoke_join(j['id'])
        with self.assertRaises(Problem): self.store.enroll(j['code'],'x')
        t=self.store.enroll(self.store.create_join()['code'],'x'); self.store.revoke_agent('x'); self.assertIsNone(self.store.agent_actor(t))
    def test_validation(self):
        for bad in (None,'','a b','../x','x'*80):
            with self.assertRaises(Problem): self.store.enroll(self.store.create_join()['code'],bad)
        for bad in (0,59,10**9,True,'900'):
            with self.assertRaises(Problem): self.store.create_join(ttl=bad)
    def test_limiter(self):
        c=Clock(); l=FailureLimiter(limit=2,window=10,clock=c)
        l.fail('a'); self.assertFalse(l.blocked('a')); l.fail('a'); self.assertTrue(l.blocked('a')); self.assertFalse(l.blocked('b'))
        c.t+=11; self.assertFalse(l.blocked('a'))

class EnrollHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.store=Store(self.temp.name+'/db')
        self.server=make_server(self.store,{'a'*32:{'role':'admin'}},port=0); self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base='http://127.0.0.1:%d'%self.server.server_port
    def tearDown(self): self.server.shutdown(); self.server.server_close(); self.thread.join(); self.store.db.close(); self.temp.cleanup()
    def req(self,path,token=None,body=None):
        h={'Authorization':'Bearer '+token} if token else {}
        r=urllib.request.Request(self.base+path,headers=h,data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(r) as res: return res.status,json.load(res)
        except urllib.error.HTTPError as e: return e.code,json.load(e)
    def test_flow_and_agent_token_works(self):
        self.assertEqual(self.req('/api/enroll/tokens',None,{})[0],401)
        status,j=self.req('/api/enroll/tokens','a'*32,{'ttl':600}); self.assertEqual(status,201)
        status,e=self.req('/api/enroll',None,{'code':j['code'],'node':'studio'}); self.assertEqual(status,201)
        self.assertEqual(self.req('/api/agent/heartbeat',e['token'],{'budgetGiB':8,'runtimes':['demo']})[0],200)
        self.assertEqual(self.req('/api/state',e['token'])[0],403)   # agents stay confined to /api/agent/*
        self.assertEqual(self.req('/api/enroll',None,{'code':j['code'],'node':'studio2'})[0],403)
        self.assertEqual([x['state'] for x in self.req('/api/enroll/tokens','a'*32)[1]],['used'])
        self.assertEqual(self.req('/api/nodes/token/revoke','a'*32,{'id':'studio'})[0],200)
        self.assertEqual(self.req('/api/agent/heartbeat',e['token'],{'budgetGiB':8,'runtimes':['demo']})[0],401)
    def test_bad_codes_are_rate_limited(self):
        for _ in range(8): self.assertEqual(self.req('/api/enroll',None,{'code':'WRONG-CODE1','node':'x'})[0],403)
        self.assertEqual(self.req('/api/enroll',None,{'code':'WRONG-CODE1','node':'x'})[0],429)
    def test_redeem_helper(self):
        import os, sys
        sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','scripts'))
        import enrollment
        j=self.store.create_join('studio'); token=enrollment.redeem(self.base,j['code'],'studio')
        self.assertEqual(self.req('/api/agent/heartbeat',token,{'budgetGiB':8,'runtimes':['demo']})[0],200)
        with self.assertRaises(SystemExit): enrollment.redeem(self.base,j['code'],'studio')
        with self.assertRaises(SystemExit): enrollment.redeem('http://example.com','X','a')
        with self.assertRaises(SystemExit): enrollment.redeem(self.base,'X','bad id')
if __name__=='__main__': unittest.main()


class ConcurrencyTests(unittest.TestCase):
    """The server shares one SQLite connection between handler threads, so every database access must hold store.lock.
    Agent authentication reads the token table on each request; this once raced with heartbeats ('database table is locked')."""
    def test_agent_auth_does_not_race_with_heartbeats(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            store=Store(d+'/db'); token=store.enroll(store.create_join()['code'],'mini'); errors=[]; stop=threading.Event()
            def auth():
                while not stop.is_set():
                    try: assert store.agent_actor(token)['node']=='mini'
                    except Exception as e: errors.append(repr(e)); return
            def beat():
                for _ in range(400):
                    try: store.register('mini',dict(budgetGiB=8,runtimes=['demo']))
                    except Exception as e: errors.append(repr(e)); return
            readers=[threading.Thread(target=auth) for _ in range(4)]; writer=threading.Thread(target=beat)
            [t.start() for t in readers]; writer.start(); writer.join(); stop.set(); [t.join() for t in readers]
            store.db.close()
            self.assertEqual(errors,[])
