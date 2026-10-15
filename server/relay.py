# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""Bounded outbound agent relay. Workers remain on loopback; no inbound Mac port is required.

Requests are ephemeral: control-plane restart fails active calls, never replays them.
Each exchange is fenced by the live serve job's node and lease.
"""
import base64
import collections
import json
import threading
import time
import uuid
from urllib.parse import urlsplit
from server.core import Problem


class AgentRelay:
    def __init__(self, store, timeout=180, max_pending=64, max_bytes=4*1024*1024):
        self.store=store; self.timeout=timeout; self.max_pending=max_pending; self.max_bytes=max_bytes
        self.condition=threading.Condition(); self.requests={}

    def serving(self,node,job,lease=None):
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
            host=self.store.db.execute('SELECT seen FROM nodes WHERE id=?',(node,)).fetchone()
            if not row or row['node']!=node or row['state']!='running' or (row['expires'] or 0)<=self.store.clock() or not host or self.store.clock()-host['seen']>30:
                raise Problem('serve lease is not live',409)
            if lease is not None and row['lease']!=lease: raise Problem('stale relay lease',409)
            spec=json.loads(row['body'])
            if spec.get('kind')!='serve': raise Problem('not a serve job',409)
            model=self.store.db.execute('SELECT body FROM models WHERE id=?',(spec.get('modelId'),)).fetchone()
            obj=json.loads(model['body']) if model else {}
            if obj.get('deployJob')!=job or not obj.get('agentRelay'): raise Problem('replica not ready',503)
            endpoints=obj.get('endpoints',[])
            if len(endpoints)!=1: raise Problem('invalid relay endpoint',503)
            url=endpoints[0]; parsed=urlsplit(url)
            if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
                raise Problem('relay endpoint must be an IPv4 loopback origin',503)
            return url.rstrip('/')

    def open(self,node,job,body):
        self.serving(node,job)
        ident=uuid.uuid4().hex
        with self.condition:
            if len(self.requests)>=self.max_pending: raise Problem('relay capacity exceeded',429)
            self.requests[ident]=dict(node=node,job=job,body=body,claimed=False,queue=collections.deque(),seq=0,total=0,done=False,deadline=time.monotonic()+self.timeout,error=None)
        return ident

    def poll(self,node,job,lease):
        endpoint=self.serving(node,job,lease)
        with self.condition:
            for ident,r in self.requests.items():
                if r['node']==node and r['job']==job and not r['claimed'] and time.monotonic()<r['deadline']:
                    r['claimed']=True
                    return dict(id=ident,endpoint=endpoint,body=r['body'])
        return None

    def push(self,node,job,lease,body):
        self.serving(node,job,lease)
        ident=body.get('request'); seq=body.get('seq'); data=body.get('data',''); done=body.get('done',False)
        if type(seq) is not int or not isinstance(data,str) or len(data)>45000 or type(done) is not bool: raise Problem('invalid relay chunk')
        try: chunk=base64.b64decode(data,validate=True)
        except (ValueError,TypeError): raise Problem('invalid relay data')
        if len(chunk)>32768: raise Problem('relay chunk too large',413)
        error=body.get('error')
        if error is not None and not isinstance(error,str): raise Problem('invalid relay error')
        with self.condition:
            r=self.requests.get(ident)
            if not r or r['node']!=node or r['job']!=job or not r['claimed'] or r['done'] or time.monotonic()>=r['deadline']: raise Problem('stale relay request',409)
            if seq!=r['seq']: raise Problem('out of order relay chunk',409)
            if r['total']+len(chunk)>self.max_bytes: raise Problem('relay response too large',413)
            # Bounded queue also applies when the caller reads slowly.
            if sum(map(len,r['queue']))+len(chunk)>262144: raise Problem('relay backpressure',429)
            r['seq']+=1; r['total']+=len(chunk)
            if chunk: r['queue'].append(chunk)
            r['done']=done or error is not None
            r['error']='inference replica failed' if error else None
            self.condition.notify_all()

    def chunks(self,ident):
        try:
            while True:
                with self.condition:
                    r=self.requests.get(ident)
                    if r is None: raise Problem('relay request closed',502)
                    if time.monotonic()>=r['deadline']: raise Problem('inference relay timed out',504)
                    node,job=r['node'],r['job']
                    if r['queue']: chunk=r['queue'].popleft()
                    elif r['done']:
                        if r['error']: raise Problem(r['error'],502)
                        return
                    else:
                        self.condition.wait(min(0.25,max(0,r['deadline']-time.monotonic())))
                        chunk=None
                self.serving(node,job)
                if chunk is not None: yield chunk
        finally: self.close(ident)

    def close(self,ident):
        with self.condition:
            self.requests.pop(ident,None); self.condition.notify_all()
