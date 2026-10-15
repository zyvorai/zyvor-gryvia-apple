# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""Fleet scenarios: different local paths, live memory, fencing, relay failures and dataset leakage."""
import base64
import concurrent.futures
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from server.core import Store, Problem
from server.relay import AgentRelay
from server.inference import Gateway
from server.app import make_server
from tests.test_inference import Worker
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtimes'))
import _common
import mlx_lora


class FleetScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.now=1000
        self.s=Store(self.tmp.name+'/db',clock=lambda:self.now)
        self.beat('a'); self.beat('b')

    def tearDown(self): self.s.db.close(); self.tmp.cleanup()

    def beat(self,node,**kw):
        self.s.register(node,dict(budgetGiB=16,runtimes=['demo','serve','train','download','quantize'],**kw))

    def spec(self,**kw): return dict(runtime='demo',memoryGiB=2,**kw)

    def test_model_stays_on_producing_mac(self):
        self.s.model('m',dict(memoryGiB=2,path='/a/models/m',node='a',sha256='a'*64))
        job=self.s.submit('default',self.spec(modelId='m',args=['{{model.path}}']))
        self.assertIsNone(self.s.claim('b'))
        claim=self.s.claim('a')
        self.assertEqual(claim['id'],job)
        self.assertEqual(claim['spec']['args'],['/a/models/m'])
        self.assertEqual(claim['spec']['inputs'],[dict(path='/a/models/m',sha256='a'*64)])

    def test_dataset_and_model_on_different_macs_wait_instead_of_failing_runtime(self):
        self.s.model('m',dict(memoryGiB=2,path='/a/m',node='a'))
        self.s.dataset('d',dict(path='/b/d',status='ready',node='b'))
        self.s.submit('default',self.spec(modelId='m',datasetId='d',args=['{{model.path}}','{{dataset.path}}']))
        self.assertIsNone(self.s.claim('a')); self.assertIsNone(self.s.claim('b'))
        self.assertIn('artifact is on',self.s.snapshot()['jobs'][0]['reason'])

    def test_missing_placeholder_artifact_waits(self):
        self.s.submit('default',self.spec(datasetId='missing',args=['{{dataset.path}}']))
        self.assertIsNone(self.s.claim('a'))
        self.assertIn('missing datasetId',self.s.snapshot()['jobs'][0]['reason'])

    def test_other_tenant_artifact_not_executed(self):
        self.s.model('m',dict(memoryGiB=2,path='/m',tenants=['private']))
        self.s.submit('default',self.spec(modelId='m'))
        self.assertIsNone(self.s.claim('a'))

    def test_live_memory_and_workingset_gate(self):
        job=self.s.submit('default',self.spec())
        self.beat('a',availableGiB=2.5,memoryHeadroomGiB=1)
        self.assertIsNone(self.s.claim('a'))
        self.beat('a',availableGiB=8,metalWorkingSetGiB=1)
        self.assertIsNone(self.s.claim('a'))
        self.beat('a',availableGiB=8,metalWorkingSetGiB=8)
        self.assertEqual(self.s.claim('a')['id'],job)

    def test_critical_pressure_cancels_and_holds_reservation_until_ack(self):
        jid=self.s.submit('default',self.spec()); claim=self.s.claim('a')
        self.beat('a',pressure='critical')
        reply=self.s.renew('a',jid,claim['lease'])
        self.assertTrue(reply['cancel']); self.assertEqual(reply['reason'],'critical memory pressure')
        self.assertEqual(self.s.snapshot()['jobs'][0]['state'],'cancelling')
        self.s.complete('a',jid,claim['lease'],False,{})
        self.assertEqual(self.s.snapshot()['jobs'][0]['state'],'cancelled')

    def test_telemetry_rejects_nan_negative_bool_and_unknown_pressure(self):
        for extra in [dict(availableGiB=float('nan')),dict(availableGiB=-1),dict(memoryHeadroomGiB=True),dict(metalWorkingSetGiB=float('inf')),dict(pressure='oops')]:
            with self.subTest(extra=extra), self.assertRaises(Problem): self.beat('a',**extra)

    def test_chain_policy_and_recheck_at_claim(self):
        self.s.require_verified_chain=True
        self.s.model('m',dict(memoryGiB=2,path='/m',provenance=dict(verified=True,chainVerified=False)))
        with self.assertRaises(Problem): self.s.submit('default',dict(runtime='serve',kind='serve',memoryGiB=2,modelId='m'))
        self.s.model('m',dict(memoryGiB=2,path='/m',provenance=dict(verified=True,chainVerified=True)))
        self.s.submit('default',dict(runtime='serve',kind='serve',memoryGiB=2,modelId='m'))
        self.s.model('m',dict(memoryGiB=2,path='/m'))
        self.assertIsNone(self.s.claim('a'))

    def test_fit_changes_with_context_and_honors_node_gate_and_tenant_quota(self):
        short=self.s.fit(dict(paramsB=1,quant='q4',contextTokens=1024))
        long=self.s.fit(dict(paramsB=1,quant='q4',contextTokens=32768))
        self.assertGreater(long['estimatedGiB'],short['estimatedGiB'])
        self.beat('a',pressure='warning')
        fit=self.s.fit(dict(paramsB=1,quant='q4'))
        self.assertEqual(fit['nodes'][0]['reason'],'memory pressure')
        self.s.tenant('tiny',0.5)
        self.assertFalse(any(n['fits'] for n in self.s.fit(dict(paramsB=1),'tiny')['nodes']))
        for body in [dict(paramsB=True),dict(paramsB=1,concurrency=0),dict(paramsB=1,kvHeads=float('nan'))]:
            with self.assertRaises(Problem): self.s.fit(body)


class RelayScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.now=1000
        self.s=Store(self.tmp.name+'/db',clock=lambda:self.now)
        self.s.register('remote',dict(budgetGiB=8,runtimes=['serve']))
        self.s.model('m',dict(memoryGiB=1,path='/remote/m',node='remote'))
        self.jid=self.s.submit('default',dict(runtime='serve',kind='serve',modelId='m',memoryGiB=2))
        self.claim=self.s.claim('remote'); self.lease=self.claim['lease']
        self.s.logs('remote',self.jid,self.lease,[json.dumps(dict(kind='endpoint',url='http://127.0.0.1:12345',agentRelay=True))])
        self.relay=AgentRelay(self.s,timeout=2)
        self.g=Gateway(relay=self.relay)
        self.body=dict(model='m',messages=[dict(role='user',content='hi')])

    def tearDown(self): self.s.db.close(); self.tmp.cleanup()

    def poll(self): return self.relay.poll('remote',self.jid,self.lease)
    def push(self,ident,data=b'',**kw):
        self.relay.push('remote',self.jid,self.lease,dict(request=ident,seq=0,data=base64.b64encode(data).decode(),done=True,**kw))

    def test_outbound_agent_poll_roundtrip_for_json(self):
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future=pool.submit(self.g.chat,self.s,'default',self.body)
            item=None
            for _ in range(100):
                item=self.poll()
                if item: break
                time.sleep(0.01)
            self.assertIsNotNone(item)
            self.assertNotIn('Authorization',json.dumps(item))
            self.assertEqual(set(item['body']),{'model','messages','max_tokens','stream'})
            self.push(item['id'],b'{"choices": [{"message": {"content": "remote Mac"}}]}')
            self.assertEqual(future.result(timeout=2)['choices'][0]['message']['content'],'remote Mac')
        self.assertEqual(self.g.calls['default'],0); self.assertEqual(self.relay.requests,{})

    def test_stream_preserves_bytes_and_client_cancellation_releases(self):
        it=self.g.stream(self.s,'default',dict(self.body,stream=True))
        item=self.poll(); self.push(item['id'],b'data: {"choices": []}\n\ndata: [DONE]\n\n')
        self.assertIn(b'[DONE]',b''.join(it)); self.assertEqual(self.g.calls['default'],0)
        it=self.g.stream(self.s,'default',dict(self.body,stream=True))
        item=self.poll(); self.push(item['id'],b'data: first\n\n')
        next(it); it.close()
        self.assertFalse(self.relay.requests); self.assertEqual(self.g.calls['default'],0)

    def test_node_lease_sequence_and_size_fencing(self):
        ident=self.relay.open('remote',self.jid,self.body); self.poll()
        with self.assertRaises(Problem): self.relay.push('other',self.jid,self.lease,dict(request=ident,seq=0))
        with self.assertRaises(Problem): self.relay.poll('remote',self.jid,'old')
        with self.assertRaises(Problem): self.relay.push('remote',self.jid,self.lease,dict(request=ident,seq=3))
        with self.assertRaises(Problem): self.push(ident,b'x'*32769)
        with self.assertRaises(Problem): self.relay.push('remote',self.jid,self.lease,dict(request=ident,seq=0,data='!'))
        self.push(ident,b'ok'); self.assertEqual(b''.join(self.relay.chunks(ident)),b'ok')

    def test_expired_lease_and_cancelled_deploy_cannot_route(self):
        self.now+=21
        with self.assertRaises(Problem): self.g.chat(self.s,'default',self.body)
        self.now-=21; self.s.cancel(self.jid)
        with self.assertRaises(Problem): self.g.stream(self.s,'default',dict(self.body,stream=True))

    def test_timeout_and_worker_error_clean_up(self):
        self.relay.timeout=0.01
        ident=self.relay.open('remote',self.jid,self.body)
        with self.assertRaises(Problem): list(self.relay.chunks(ident))
        self.assertEqual(self.relay.requests,{})
        self.relay.timeout=2
        ident=self.relay.open('remote',self.jid,self.body); self.poll()
        self.relay.push('remote',self.jid,self.lease,dict(request=ident,seq=0,error='secret worker stacktrace',done=True))
        with self.assertRaises(Problem) as error: list(self.relay.chunks(ident))
        self.assertNotIn('secret',str(error.exception.message))

    def test_relay_refuses_non_loopback_and_redirect_style_origin(self):
        for url in ['http://10.0.0.1:12','http://127.0.0.1:12/path','http://user@127.0.0.1:12','https://127.0.0.1:12']:
            self.s.logs('remote',self.jid,self.lease,[json.dumps(dict(kind='endpoint',url=url,agentRelay=True))])
            with self.subTest(url=url),self.assertRaises(Problem): self.poll()

    def test_capacity_and_lagging_reader_are_bounded(self):
        self.relay.max_pending=1
        ident=self.relay.open('remote',self.jid,self.body); self.poll()
        with self.assertRaises(Problem): self.relay.open('remote',self.jid,self.body)
        for seq in range(8):
            self.relay.push('remote',self.jid,self.lease,dict(request=ident,seq=seq,data=base64.b64encode(b'x'*32768).decode()))
        with self.assertRaises(Problem): self.relay.push('remote',self.jid,self.lease,dict(request=ident,seq=8,data=base64.b64encode(b'x').decode()))

    def test_old_serve_completion_does_not_clear_new_deployment(self):
        # Model record may already point to a newer replica during replacement.
        m=next(m for m in self.s.snapshot()['models'] if m['id']=='m')
        m.pop('id'); m['deployJob']='new-job'; self.s.model('m',m)
        self.s.complete('remote',self.jid,self.lease,False,{})
        m=next(m for m in self.s.snapshot()['models'] if m['id']=='m')
        self.assertEqual(m['deployJob'],'new-job'); self.assertTrue(m['endpoints'])


class RuntimeReliability(unittest.TestCase):
    def test_all_rows_validated_and_three_splits_are_disjoint_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'d.jsonl'
            rows=[dict(text=f'fact {n}') for n in range(30)]
            data.write_text('\n'.join(json.dumps(r) for r in rows+rows[:5]))
            self.assertEqual(mlx_lora.prepare(data,root/'one',0.1),(24,3))
            mlx_lora.prepare(data,root/'two',0.1)
            splits=[set((root/'one/data'/f'{name}.jsonl').read_text().splitlines()) for name in ['train','valid','test']]
            self.assertTrue(all(not splits[a]&splits[b] for a,b in [(0,1),(0,2),(1,2)]))
            self.assertEqual(sum(map(len,splits)),30)
            self.assertEqual((root/'one/data/train.jsonl').read_bytes(),(root/'two/data/train.jsonl').read_bytes())
            data.write_text(data.read_text()+'\ninvalid row 36')
            with self.assertRaises(ValueError): mlx_lora.prepare(data,root/'bad',0.1)

    def test_checkpoint_steps_promoted_with_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); segment=root/'segment'; adapter=root/'adapter'; segment.mkdir(); adapter.mkdir()
            (segment/'0000010_adapters.safetensors').write_bytes(b'checkpoint')
            (segment/'adapters.safetensors').write_bytes(b'final')
            mlx_lora.promote_checkpoints(segment,adapter,30)
            self.assertEqual(mlx_lora.saved_step(adapter),40)
            self.assertEqual((adapter/'0000040_adapters.safetensors').read_bytes(),b'checkpoint')

    def test_artifact_digest_detects_mutation_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,GRYVIA_MODELS_DIR=tmp):
            root=Path(tmp); model=root/'model'; model.mkdir(); file=model/'weights'; file.write_bytes(b'original')
            digest=_common.artifact_digest(model)
            with patch.dict(os.environ,GRYVIA_INPUT_MANIFEST=json.dumps([dict(path=str(model),sha256=digest)])):
                _common.verify_inputs(); file.write_bytes(b'tampered')
                with self.assertRaises(SystemExit): _common.verify_inputs()
            (model/'escape').symlink_to('/etc/hosts')
            with self.assertRaises(SystemExit): _common.artifact_digest(model)

    def test_sigterm_escalates_for_uncooperative_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'pid'
            child=f'import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); open({str(marker)!r},"w").write(str(os.getpid())); time.sleep(60)'
            code=f'import sys; sys.path.insert(0,{str(ROOT/"runtimes")!r}); from _common import run_group; run_group([sys.executable,"-c",{child!r}],timeout=100)'
            proc=subprocess.Popen([sys.executable,'-c',code])
            try:
                for _ in range(100):
                    if marker.exists() and marker.read_text(): break
                    time.sleep(0.02)
                self.assertTrue(marker.exists(),'child did not start')
                pid=int(marker.read_text()); proc.terminate()
                self.assertEqual(proc.wait(timeout=5),143)
                with self.assertRaises(ProcessLookupError): os.kill(pid,0)
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()


class RelayHTTPScenario(unittest.TestCase):
    def test_authenticated_controller_agent_and_worker_roundtrip(self):
        """Real HTTP API + separate mock runtime, with outbound polling standing in for Swift."""
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp+'/db'); worker=ThreadingHTTPServer(('127.0.0.1',0),Worker)
            server=make_server(store,{'a'*32:dict(role='admin'),'n'*32:dict(role='agent',node='mini')},port=0)
            threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (server,worker)]
            for thread in threads: thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            def call(path,body,token='n'*32):
                req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token})
                with urllib.request.urlopen(req,timeout=5) as response: return json.load(response)
            try:
                call('/api/agent/heartbeat',dict(budgetGiB=8,runtimes=['serve']))
                store.model('m',dict(memoryGiB=1))
                jid=store.submit('default',dict(runtime='serve',kind='serve',modelId='m',memoryGiB=1))
                claim=call('/api/agent/claim',{})['job']; lease=claim['lease']
                endpoint='http://127.0.0.1:'+str(worker.server_port)
                call('/api/agent/logs',dict(id=jid,lease=lease,lines=[json.dumps(dict(kind='endpoint',url=endpoint,agentRelay=True))]))
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future=pool.submit(call,'/v1/chat/completions',dict(model='m',messages=[dict(role='user',content='hi')]),'a'*32)
                    item=None
                    for _ in range(100):
                        item=call('/api/agent/relay-poll',dict(id=jid,lease=lease))['request']
                        if item: break
                        time.sleep(0.01)
                    self.assertIsNotNone(item)
                    req=urllib.request.Request(item['endpoint']+'/v1/chat/completions',data=json.dumps(item['body']).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(req) as response: data=response.read()
                    call('/api/agent/relay-push',dict(id=jid,lease=lease,request=item['id'],seq=0,data=base64.b64encode(data).decode(),done=True))
                    self.assertIn('choices',future.result(timeout=5)); self.assertNotIn('Authorization',worker.seen[0])
                self.assertEqual(call('/api/fit',dict(paramsB=1,quant='q4'),'a'*32)['assumptions']['contextTokens'],4096)
                with self.assertRaises(urllib.error.HTTPError) as error: call('/api/agent/relay-poll',dict(id=jid,lease=lease),'a'*32)
                self.assertEqual(error.exception.code,403)
            finally:
                for s in (server,worker): s.shutdown(); s.server_close()
                for t in threads: t.join()
                store.db.close()

class AttestationStatusTests(unittest.TestCase):
    def test_signed_success_cannot_be_used_for_failed_completion(self):
        from tests.test_provenance import ProvenanceFlowTests
        case=ProvenanceFlowTests(); case.setUp()
        try:
            case.s.model('m',dict(memoryGiB=1,runtime='llama',status='onboarding'))
            case.run_job(dict(runtime='download',kind='download',modelId='m'),[json.dumps(dict(kind='result',path='/m',sha256='a'*64))],tamper=dict(success=False))
            self.assertFalse(case.model()['provenance']['verified'])
            self.assertIn('signed status',case.s.attestations()[0]['why'])
        finally: case.tearDown()

class StreamEarlyCloseTests(unittest.TestCase):
    def test_close_before_first_chunk_releases_relay_and_quota(self):
        case=RelayScenarios(); case.setUp()
        try:
            stream=case.g.stream(case.s,'default',dict(case.body,stream=True))
            stream.close(); stream.close()
            self.assertEqual(case.g.calls['default'],0); self.assertFalse(case.relay.requests)
        finally: case.tearDown()


class TrainingContinuationScenario(unittest.TestCase):
    def test_failed_segment_resumes_only_remaining_steps_with_fake_mlx_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); models=root/'models'; models.mkdir()
            dataset=models/'d.jsonl'; dataset.write_text('\n'.join(json.dumps(dict(text=f'row {i}')) for i in range(30)))
            module=root/'mlx_lm'; module.mkdir(); (module/'__init__.py').write_text('')
            (module/'__main__.py').write_text('''import json,sys
from pathlib import Path
a=sys.argv
out=Path(a[a.index('--adapter-path')+1]); out.mkdir(parents=True,exist_ok=True)
n=int(a[a.index('--iters')+1]); marker=Path(__file__).parent/'first'
if not marker.exists():
 marker.write_text('yes'); n=10; status=1
else:
 assert n==20, n
 assert '--resume-adapter-file' in a
 assert Path(a[a.index('--resume-adapter-file')+1]).read_bytes()==b'checkpoint'
 status=0
(out/f'{n:07d}_adapters.safetensors').write_bytes(b'checkpoint')
(out/'adapters.safetensors').write_bytes(b'checkpoint')
(out/'adapter_config.json').write_text('{}')
print(f'Iter {n}: Val loss 1.2',flush=True)
sys.exit(status)
''')
            env=dict(os.environ,GRYVIA_MODELS_DIR=str(models),GRYVIA_JOB_ID='test-job',PYTHONPATH=str(root))
            cmd=[sys.executable,str(ROOT/'runtimes/mlx_lora.py'),'--model','org/model','--data',str(dataset),'--iters','30']
            first=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(first.returncode,1,first.stderr)
            second=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(second.returncode,0,second.stderr+second.stdout)
            rows=[json.loads(line) for line in second.stdout.splitlines() if line.startswith('{')]
            self.assertEqual(rows[-1]['completedSteps'],30)
            self.assertEqual(rows[-1]['resumeMode'],'adapter-weights-only')
            self.assertIn(30,[r['step'] for r in rows if r.get('kind')=='metric'])
            self.assertEqual(len(rows[-1]['sha256']),64)
            dataset.write_text(dataset.read_text()+'\n'+json.dumps(dict(text='changed')))
            third=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(third.returncode,0); self.assertIn('inputs changed',third.stderr)

class ArtifactReplicaScenario(unittest.TestCase):
    def test_stage_verified_copy_and_resolve_different_paths_on_second_mac(self):
        case=FleetScenarios(); case.setUp()
        try:
            case.s.model('m',dict(memoryGiB=1,path='/a/m',node='a',sha256='a'*64,paramsB=1))
            case.s.dataset('d',dict(path='/a/d',node='a',sha256='b'*64,status='ready'))
            for kind,ident,path,digest in [('model','m','/b/model','a'*64),('dataset','d','/b/data','b'*64)]:
                case.s.stage_artifact(dict(kind=kind,id=ident,node='b',path=path,sha256=digest))
            case.s.submit('default',case.spec(modelId='m',datasetId='d',args=['{{model.path}}','{{dataset.path}}']))
            claim=case.s.claim('b')
            self.assertEqual(claim['spec']['args'],['/b/model','/b/data'])
            self.assertEqual([i['path'] for i in claim['spec']['inputs']],['/b/model','/b/data'])
            for body in [dict(kind='model',id='m',node='b',path='/b/model',sha256='c'*64),dict(kind='model',id='m',node='missing',path='/b/model',sha256='a'*64)]:
                with self.assertRaises(Problem): case.s.stage_artifact(body)
        finally: case.tearDown()

class CheckpointPlacementScenario(unittest.TestCase):
    def test_yielded_training_returns_to_its_checkpoint_mac(self):
        case=FleetScenarios(); case.setUp()
        try:
            jid=case.s.submit('default',dict(runtime='train',kind='train',memoryGiB=1))
            claim=case.s.claim('a')
            case.s.set_policy('a',dict(mode='paused'))
            case.s.complete('a',jid,claim['lease'],False,{})
            self.assertIsNone(case.s.claim('b'))
            case.s.set_policy('a',dict(mode='always'))
            self.assertEqual(case.s.claim('a')['id'],jid)
            with self.assertRaises(Problem): case.s.submit('default',dict(runtime='train',kind='train',memoryGiB=1,checkpointNode='a'))
        finally: case.tearDown()

class NewCLIWorkflow(unittest.TestCase):
    def test_stage_fit_and_deploy_on_another_mac_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); models=root/'models'; models.mkdir(); file=models/'m.gguf'; file.write_bytes(b'model')
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            store=Store(str(root/'db')); store.register('b',dict(budgetGiB=8,runtimes=['serve']))
            store.model('m',dict(memoryGiB=1,paramsB=1,quant='q4',path='/a/m.gguf',node='a',sha256=digest))
            server=make_server(store,{'a'*32:dict(role='admin')},port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            env=dict(os.environ,GRYVIA_ADMIN_TOKEN='a'*32,GRYVIA_MODELS_DIR=str(models))
            command=[sys.executable,str(ROOT/'scripts/gryvia.py'),'--server',f'http://127.0.0.1:{server.server_port}']
            def cli(*args):
                result=subprocess.run(command+list(args),env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                return json.loads(result.stdout)
            try:
                cli('stage','model','m','--node','b','--path',str(file))
                self.assertTrue(cli('fit','--model','m')['nodes'][0]['fits'])
                result=cli('deploy','m','--node','b')
                claim=store.claim('b')
                self.assertEqual(claim['id'],result['id']); self.assertEqual(claim['spec']['args'],['--model',str(file)])
            finally:
                server.shutdown(); server.server_close(); thread.join(); store.db.close()

class StateStreamShutdownScenario(unittest.TestCase):
    def test_server_shutdown_stops_state_stream_before_database_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp+'/db'); server=make_server(store,{'a'*32:dict(role='admin')},port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/stream',headers={'Authorization':'Bearer '+'a'*32})
            response=urllib.request.urlopen(request,timeout=3)
            self.assertTrue(response.readline().startswith(b'data: '))
            server.shutdown(); server.server_close(); thread.join()
            self.assertTrue(server.stopping.is_set())
            response.read(); response.close(); store.db.close()
