# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""Bounded OpenAI-style routing over allowlisted HTTP origins or lease-fenced outbound agents."""
import json, threading, time, urllib.request, urllib.error, urllib.parse
from server.core import Problem

class ClosingStream:
    """Release eager admission even if a caller closes before requesting its first chunk."""
    def __init__(self,iterator,cleanup): self.iterator=iterator; self.cleanup=cleanup; self.closed=False
    def __iter__(self): return self
    def __next__(self):
        if self.closed: raise StopIteration
        try: return next(self.iterator)
        except BaseException:
            self.close(); raise
    def close(self):
        if self.closed: return
        self.closed=True
        try: self.iterator.close()
        finally: self.cleanup()


class Gateway:
    def __init__(self, allowed_origins=(), max_inflight=2, allow_loopback=False, relay=None):
        if type(max_inflight) is not int or not 1<=max_inflight<=64: raise Problem('invalid inference concurrency')
        if not isinstance(allowed_origins,(list,tuple)) or not all(isinstance(x,str) for x in allowed_origins): raise Problem('invalid inference origins')
        self.relay=relay; self.allowed=set(allowed_origins);self.allow_loopback=bool(allow_loopback);self.limit=max_inflight;self.lock=threading.Lock();self.active={};self.calls={}
    def _validate(self, body, allow_stream):
        if body.get('stream') and not allow_stream:raise Problem('streaming is not supported here; use the streaming endpoint path or stream=false')
        model=body.get('model');messages=body.get('messages');maximum=body.get('max_tokens',256)
        if not isinstance(model,str) or not isinstance(messages,list) or not 1<=len(messages)<=128:raise Problem('model and messages required')
        if type(maximum) is not int or not 1<=maximum<=4096:raise Problem('max_tokens must be 1..4096')
        if not all(isinstance(m,dict) and m.get('role') in ['system','user','assistant'] and isinstance(m.get('content'),str) for m in messages):raise Problem('invalid messages')
        if sum(len(m['content']) for m in messages)>32768:raise Problem('input too long',413)
        return model,messages,maximum
    def _admit(self, store, tenant, model, exclude=()):
        """Pick an allowlisted replica and take a concurrency slot. Caller must call _release().
        Returns (catalog, endpoint, route); route is (node, job) for an agent relay replica, else None.
        Replicas in exclude are skipped (used for one failover attempt)."""
        catalog=next((m for m in store.snapshot(tenant)['models'] if m['id']==model),None)
        if not catalog:raise Problem('model not found',404)
        if catalog.get('tenants') and tenant not in catalog['tenants']:raise Problem('model not found',404)
        endpoints=catalog.get('endpoints',[])
        if not isinstance(endpoints,list):raise Problem('invalid model endpoints',503)
        candidates=[]; routes={}; refused=None
        replicas=catalog.get('replicas') or []
        if replicas:   # one entry per serve job; relay replicas are validated one by one so a dead one is skipped
            for r in replicas:
                if r.get('agentRelay'):
                    if not self.relay: continue
                    try: self.relay.serving(r.get('node'),r.get('job'))
                    except Problem as e: refused=refused or e; continue
                    key='agent-relay:'+r['node']+':'+r['job']; routes[key]=(r['node'],r['job']); candidates.append(key)
                else: candidates.extend(self._allowed([r.get('url')]))
        else:
            if self.relay and catalog.get('agentRelay'):
                node=catalog.get('endpointNode'); job=catalog.get('deployJob')
                self.relay.serving(node,job)
                key='agent-relay:'+node+':'+job; routes[key]=(node,job); candidates.append(key)
            if not catalog.get('agentRelay'): candidates.extend(self._allowed(endpoints))
        candidates=[c for c in candidates if c not in exclude]
        if not candidates:
            if refused and not exclude: raise refused
            raise Problem('no allowlisted inference replica',503)
        with self.lock:
            if self.calls.get(tenant,0)>=self.limit:raise Problem('tenant inference concurrency exceeded',429)
            endpoint=min(candidates,key=lambda e:self.active.get(e,0))
            self.active[endpoint]=self.active.get(endpoint,0)+1;self.calls[tenant]=self.calls.get(tenant,0)+1
        return catalog,endpoint,routes.get(endpoint)
    def _allowed(self, endpoints):
        out=[]
        for e in endpoints:
            if not isinstance(e,str):continue
            u=urllib.parse.urlsplit(e)
            origin=f'{u.scheme}://{u.netloc}'
            loopback=self.allow_loopback and u.scheme=='http' and u.hostname in ('127.0.0.1','localhost','::1')
            if (origin in self.allowed or loopback) and u.scheme in ['http','https'] and not u.username and not u.password and not u.query and not u.fragment and u.path in ['','/']:out.append(e.rstrip('/'))
        return out
    def _release(self, tenant, endpoint):
        with self.lock:self.active[endpoint]-=1;self.calls[tenant]-=1
    @staticmethod
    def _opener():
        # Never forward the caller's platform token to a model server.
        # Redirects are forbidden so an allowlisted origin cannot redirect to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):return None
        return urllib.request.build_opener(NoRedirect())
    def chat(self, store, tenant, body):
        model,messages,maximum=self._validate(body,False)
        tried=[]; first=None
        while True:
            try: catalog,endpoint,route=self._admit(store,tenant,model,tried)
            except Problem:
                if first: raise first   # no other replica: report the original failure
                raise
            try: return self._chat_once(store,tenant,model,catalog,endpoint,route,messages,maximum)
            except Problem as e:
                # One failover to another replica when this one is gone or answered badly; never for caller errors.
                if e.status not in (502,503,504) or tried: raise
                first=e; tried.append(endpoint)
            finally:self._release(tenant,endpoint)
    def _chat_once(self, store, tenant, model, catalog, endpoint, route, messages, maximum):
        request={'model':catalog.get('workerModel',model),'messages':messages,'max_tokens':maximum,'stream':False}
        if route:
            ident=self.relay.open(route[0],route[1],request)
            try: result=json.loads(b''.join(self.relay.chunks(ident)))
            except (ValueError,UnicodeError): raise Problem('invalid inference response',502)
            if not isinstance(result,dict) or not isinstance(result.get('choices'),list): raise Problem('invalid inference response',502)
            with store.lock: store.event('inference.completed',tenant,model)
            return result
        req=urllib.request.Request(endpoint+'/v1/chat/completions',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
        try:
            with self._opener().open(req,timeout=180) as r:
                data=r.read(4*1024*1024+1)
                if len(data)>4*1024*1024:raise Problem('worker response too large',502)
                result=json.loads(data)
        except (urllib.error.URLError,ValueError):raise Problem('inference replica failed',502)
        if not isinstance(result,dict) or not isinstance(result.get('choices'),list):raise Problem('invalid inference response',502)
        with store.lock:store.event('inference.completed',tenant,model)
        return result
    def _open_stream(self, catalog, endpoint, route, model, messages, maximum):
        """Open the upstream stream: a relay request id, or an HTTP response. Raises Problem before any byte is read."""
        request={'model':catalog.get('workerModel',model),'messages':messages,'max_tokens':maximum,'stream':True}
        if route: return self.relay.open(route[0],route[1],request)
        req=urllib.request.Request(endpoint+'/v1/chat/completions',data=json.dumps(request).encode(),headers={'Content-Type':'application/json','Accept':'text/event-stream'})
        try: return self._opener().open(req,timeout=30)
        except (urllib.error.URLError,ValueError): raise Problem('inference replica failed',502)
    def stream(self, store, tenant, body, max_bytes=4*1024*1024, max_seconds=180):
        """Relay a replica's server-sent events. Validation and admission happen before the first byte; yields raw SSE chunks.
        Bounded in bytes and wall time; the concurrency slot is released when the generator is closed."""
        model,messages,maximum=self._validate(body,True)
        tried=[]; first=None
        while True:   # failover only before the first byte: opening the connection, never mid-stream
            try: catalog,endpoint,route=self._admit(store,tenant,model,tried)
            except Problem:
                if first: raise first
                raise
            try: opened=self._open_stream(catalog,endpoint,route,model,messages,maximum)
            except Problem as e:
                self._release(tenant,endpoint)
                if e.status not in (502,503,504) or tried: raise
                first=e; tried.append(endpoint); continue
            except BaseException:
                self._release(tenant,endpoint); raise
            break
        if route:
            ident=opened
            def relay_gen():
                try:
                    total=0; started=time.monotonic()
                    for chunk in self.relay.chunks(ident):
                        total+=len(chunk)
                        if total>max_bytes or time.monotonic()-started>max_seconds: break
                        yield chunk
                    with store.lock: store.event('inference.streamed',tenant,model)
                finally:
                    self.relay.close(ident)
            return ClosingStream(relay_gen(),lambda:(self.relay.close(ident),self._release(tenant,endpoint)))
        resp=opened
        def gen():
            total=0;started=time.monotonic()
            try:
                with resp:
                    while True:
                        chunk=resp.readline()
                        if not chunk:break
                        total+=len(chunk)
                        if total>max_bytes or time.monotonic()-started>max_seconds:break
                        yield chunk
                with store.lock:store.event('inference.streamed',tenant,model)
            finally:resp.close()
        return ClosingStream(gen(),lambda:(resp.close(),self._release(tenant,endpoint)))
