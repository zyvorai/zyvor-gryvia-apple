#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""macOS CPU-only integration: real Swift agent relays JSON and SSE from a mock model server.

Run after swift build --product gryvia-agent. No MLX, llama.cpp, model download or GPU benchmark.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.app import make_server
from server.core import Store


class MockWorker(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        if self.headers.get('Authorization'):
            self.send_error(403); return
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream' if body.get('stream') else 'application/json')
        self.end_headers()
        if body.get('stream'):
            for part in ['Swift',' relay',' works']:
                self.wfile.write(('data: '+json.dumps(dict(choices=[dict(delta=dict(content=part))]))+'\n\n').encode()); self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
        else: self.wfile.write(json.dumps(dict(choices=[dict(message=dict(content='Swift relay works'))])).encode())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent',default='native/.build/debug/gryvia-agent'); args=parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); store=Store(str(root/'db'))
        admin=secrets.token_urlsafe(32); token=secrets.token_urlsafe(32)
        server=make_server(store,{admin:dict(role='admin'),token:dict(role='agent',node='smoke')},port=0)
        worker=ThreadingHTTPServer(('127.0.0.1',0),MockWorker)
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (server,worker)]
        for t in threads: t.start()
        base=f'http://127.0.0.1:{server.server_port}'; endpoint=f'http://127.0.0.1:{worker.server_port}'
        runtime=root/'serve.py'
        runtime.write_text('import json,time\nprint(json.dumps(dict(kind="endpoint",url='+repr(endpoint)+',agentRelay=True)),flush=True)\nwhile True: time.sleep(1)\n')
        config=root/'agent.json'; config.write_text(json.dumps(dict(server=base,budgetGiB=1,runtimes=dict(serve=dict(executable=sys.executable,prefix=[str(runtime)])))))
        with (root/'agent.log').open('w') as log:
            agent=subprocess.Popen([str(Path(args.agent).resolve()),str(config)],env=dict(os.environ,GRYVIA_AGENT_TOKEN=token),stdout=log,stderr=log)
            try:
                store.model('smoke',dict(memoryGiB=0.1))
                jid=store.submit('default',dict(runtime='serve',kind='serve',modelId='smoke',memoryGiB=0.1,timeoutSeconds=90))
                for _ in range(300):
                    if agent.poll() is not None: raise RuntimeError('Swift agent exited; see local agent log')
                    model=next(m for m in store.snapshot()['models'] if m['id']=='smoke')
                    if model.get('agentRelay'): break
                    time.sleep(0.1)
                else: raise RuntimeError('serve readiness timeout')
                for stream in (False,True):
                    body=dict(model='smoke',messages=[dict(role='user',content='hello')],stream=stream)
                    req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+admin,'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=15) as response: data=response.read()
                    if stream:
                        assert b'[DONE]' in data and b'works' in data,data
                    else: assert json.loads(data)['choices'][0]['message']['content']=='Swift relay works'
                store.cancel(jid)
                print('Swift agent outbound relay: JSON + SSE + no token forwarding: PASS')
            finally:
                agent.terminate()
                try: agent.wait(timeout=5)
                except subprocess.TimeoutExpired: agent.kill(); agent.wait()
                for s in (server,worker): s.shutdown(); s.server_close()
                for t in threads: t.join()
                store.db.close()


if __name__=='__main__': main()
