#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""Two real gryvia-agent processes on THIS Mac against a local control plane. Not a two-Mac test: it exercises enrolment
with join codes, one agent per node id, concurrent placement, and what happens when an agent is killed and restarted
mid-job. Everything runs on loopback in a temp directory. Needs `swift build --product gryvia-agent` first."""
import json, os, signal, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import enrollment
AGENT = ROOT / "native/.build/debug/gryvia-agent"
results = []

def check(name, ok, detail=""):
    results.append(ok); print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail else ""), flush=True)
    return ok

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def main():
    if not AGENT.exists(): raise SystemExit(f"build the agent first: (cd native && swift build --product gryvia-agent)  [{AGENT}]")
    work = Path(tempfile.mkdtemp(prefix="gryvia-multi-")); procs = []
    port = free_port(); server = f"http://127.0.0.1:{port}"
    subprocess.run([sys.executable, str(ROOT / "scripts/configure.py"), "--output", str(work / "cfg"), "--server", server], check=True, capture_output=True)
    env_text = (work / "cfg/credentials.env").read_text()
    admin = next(l.split("=", 1)[1].strip().strip("'\"") for l in env_text.splitlines() if "ADMIN_TOKEN" in l)
    def api(path, body=None):
        req = urllib.request.Request(server + "/api/" + path, headers={"Authorization": "Bearer " + admin}, data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=10) as r: return json.load(r)
    def spawn(argv, log, **kw):
        p = subprocess.Popen(argv, stdout=open(work / log, "ab"), stderr=subprocess.STDOUT, start_new_session=True, **kw); procs.append(p); return p
    def job(ident): return next(j for j in api("state")["jobs"] if j["id"] == ident)
    def wait(pred, timeout, step=0.5):
        end = time.time() + timeout
        while time.time() < end:
            if pred(): return True
            time.sleep(step)
        return False
    def demo_children(seconds):
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
        return [l.split(None, 2) for l in out.splitlines() if "runtimes/demo.py" in l and f"--seconds {seconds}" in l]
    try:
        spawn([sys.executable, "-m", "server.app", "--config", str(work / "cfg/config.json"), "--db", str(work / "db"), "--port", str(port)], "server.log", cwd=ROOT)
        wait(lambda: subprocess.run(["curl", "-fsS", server + "/healthz"], capture_output=True).returncode == 0, 10)
        # enrol two nodes with join codes; the agents get only their own token, through the environment
        agents = {}
        for node in ("agent-a", "agent-b"):
            code = api("enroll/tokens", {"node": node, "ttl": 300})["code"]
            token = enrollment.redeem(server, code, node)
            cfg = work / f"{node}.json"; cfg.write_text((work / "cfg/agent.json").read_text()); agents[node] = (cfg, token)
        check("join codes enrolled two nodes", True)
        def start(node):
            cfg, token = agents[node]
            return spawn([str(AGENT), str(cfg)], f"{node}.log", env={**os.environ, "GRYVIA_AGENT_TOKEN": token})
        running = {n: start(n) for n in agents}
        check("both agents online", wait(lambda: sum(n["online"] for n in api("state")["nodes"]) >= 2, 20), "2 nodes heartbeating")
        a = api("jobs", {"runtime": "demo", "memoryGiB": 1, "node": "agent-a", "retries": 0, "timeoutSeconds": 120, "args": ["--seconds", "26"]})["id"]
        b = api("jobs", {"runtime": "demo", "memoryGiB": 1, "node": "agent-b", "retries": 0, "timeoutSeconds": 120, "args": ["--seconds", "27"]})["id"]
        ok = wait(lambda: job(a)["state"] == "running" and job(b)["state"] == "running", 20)
        check("one job running on each agent at the same time", ok and job(a)["node"] == "agent-a" and job(b)["node"] == "agent-b")
        # wait out the server's reconcile grace period, then kill agent-b without warning and restart it at once
        time.sleep(12)
        t_kill = time.time(); os.killpg(running["agent-b"].pid, signal.SIGKILL); running["agent-b"].wait()
        time.sleep(1); running["agent-b"] = start("agent-b")
        gone = wait(lambda: job(b)["state"] != "running", 40, 0.25); took = time.time() - t_kill
        j = job(b)
        check("restarted agent's empty job list releases the lost job", gone and j["state"] == "failed", f"{j['state']} after {took:.1f}s; reason: {j['reason']!r}")
        check("released faster than the 20 s lease would have expired", gone and took < 15, f"{took:.1f}s")
        check("the other agent's job was untouched", job(a)["state"] in ("running", "succeeded"))
        orphans = demo_children(27)
        print(f"INFO  orphaned job process after agent kill: {'YES, still running (pids ' + ', '.join(o[0] for o in orphans) + ')' if orphans else 'none seen'}", flush=True)
        check("job on the surviving agent completes", wait(lambda: job(a)["state"] == "succeeded", 40), job(a)["state"])
        check("restarted agent is online and takes new work", wait(lambda: api("state")["nodes"] and all(n["online"] for n in api("state")["nodes"]), 15)
              and (lambda c: wait(lambda: job(c)["state"] == "succeeded", 30))(api("jobs", {"runtime": "demo", "memoryGiB": 1, "node": "agent-b", "args": ["--seconds", "2"]})["id"]))
    finally:
        for p in procs:
            try: os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): pass
        subprocess.run(["pkill", "-f", "runtimes/demo.py --seconds 2[67]"], capture_output=True)
        print(f"logs kept in {work}" if not all(results) else "", flush=True)
    print("PASS: multi-agent smoke" if results and all(results) else "FAIL: multi-agent smoke"); sys.exit(0 if results and all(results) else 1)

if __name__ == "__main__": main()
