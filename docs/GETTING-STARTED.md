# Getting started (for people who run things)

Gryvia schedules jobs across your Macs and serves models from them behind one OpenAI-style endpoint. This page takes you from nothing to a model answering requests, then to two replicas and automatic cleanup. Everything below uses commands that ship in this repository.

**Licence in one line:** reading, building, evaluating and testing is free; running it for real work needs a plan (see the [pricing](https://zyvorai.github.io/zyvor-gryvia-apple/#download)). `LICENSE` is the authority.

**You need:** Apple Silicon Mac(s) on macOS 15+, Python 3.14 for the control plane (standard library only), Xcode command-line tools to build the agent. A second Mac is optional.

## 1. Run the control plane and an agent (5 minutes)

```bash
git clone https://github.com/zyvorai/zyvor-gryvia-apple && cd zyvor-gryvia-apple
make run-server            # terminal 1: creates ./local with tokens (mode 0600), listens on 127.0.0.1:8443
make run-agent             # terminal 2: this Mac becomes a worker
make doctor                # checks the server, your token and that an agent registered
open http://127.0.0.1:8443 # paste GRYVIA_ADMIN_TOKEN from local/credentials.env
```

Prefer an installed app? `brew install --cask zyvorai/tap/gryvia` installs the notarized `Gryvia.app` (Apple silicon, macOS 15+); This guide uses a source checkout, so the `make` and `scripts/gryvia.py` commands need the repository.

Press **Run demo job** in the dashboard to see admission, a lease and a result. `python3 scripts/gryvia.py quickstart` always tells you the next step.

Load the tokens into your shell for the CLI and curl:

```bash
set -a; . local/credentials.env; set +a   # GRYVIA_ADMIN_TOKEN, GRYVIA_TENANT_TOKEN, GRYVIA_AGENT_TOKEN
alias gryvia='python3 scripts/gryvia.py'
```

## 2. Get a model and check it fits

```bash
gryvia fit --params-b 8 --quant q4 --context-tokens 4096          # memory estimate before you download
gryvia onboard my-llama --repo bartowski/Llama-3.2-1B-Instruct-GGUF \
        --file Llama-3.2-1B-Instruct-Q4_K_M.gguf --quant Q4_K_M --params-b 1.2
gryvia models                                                       # wait for status "ready"
```

Downloads come only from huggingface.co or hf.co, with a size cap and a recorded SHA-256. The `fit` figure is an estimate, not a guarantee.

## 3. Deploy and call it

```bash
gryvia deploy my-llama
gryvia models      # an endpoint appears once llama-server is up
curl -s http://127.0.0.1:8443/v1/chat/completions \
  -H "Authorization: Bearer $GRYVIA_TENANT_TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"my-llama","messages":[{"role":"user","content":"Say hi"}]}'
```

Add `"stream": true` for server-sent events. The model server listens on the worker's loopback only; the agent relays requests outbound-polled, so the worker needs no open port and your platform token never reaches the model server.

## 4. Serve from several Macs (v0.4)

Enrol a second Mac with a single-use join code (no config edit or server restart):

```bash
gryvia enroll create --node mini-02          # prints a code such as K7M2P-9XQ4R; valid 15 minutes, one use
# on the new Mac:
python3 scripts/install-agent.py --binary /path/to/gryvia-agent --config agent.json \
  --join https://your-control-plane:8443 --code K7M2P-9XQ4R --node mini-02
```

The same code can be created from **Mac fleet → Add a Mac** in the web dashboard. The server stores only hashes of codes and tokens; a bad code is rate-limited (8 failures per 5 minutes per address); `gryvia revoke-node mini-02` invalidates a Mac's token. Static tokens in `config.json` keep working. Over plain HTTP only loopback is accepted, so use HTTPS for a remote control plane. The older route (`make deploy MINI=your-mac` over ssh) still works. Then copy the model to it with `stage`, then deploy one replica per Mac:

```bash
gryvia stage model my-llama --node mini-02 --path /Users/me/models/Llama-3.2-1B-Instruct-Q4_K_M.gguf
gryvia deploy my-llama --node mini-01 --node mini-02
```

The gateway sends each request to the replica with the fewest in flight. If one is unreachable it tries one other replica before returning 502; a stream fails over only before its first byte. When one replica's job ends the others keep serving. `gryvia undeploy my-llama` stops them all. There is no autoscaler: a lost replica is not replaced for you. Cross-Mac behaviour has not been measured on two physical Macs yet.

## 5. Free memory automatically (v0.4)

Deployments hold their reservation until stopped. To stop ones nobody uses:

- **By hand:** Overview → *Idle deployments* in the dashboard, or `POST /api/models/evict-idle {"seconds": 3600}` (admin token).
- **Automatically, opt-in:** add `"autoEvictIdleSeconds": 3600` to `config.json` (0 or absent = off, minimum 60) or start the server with `--auto-evict-idle 3600`. Every `autoEvictIntervalSeconds` (default 60) it cancels serve jobs for models with no gateway traffic in that window.

Idle is measured from gateway requests only; direct calls to a worker's port are not seen. An evicted model returns to `ready`, requests get 503 until you deploy it again, and nothing redeploys it for you.

## Using the Mac app

Open **Gryvia.app** (or `brew install --cask zyvorai/tap/gryvia`). The first launch shows a short Welcome; reopen it from **Help**. Paste an admin token once; it goes to your login Keychain. **⌘K** opens a command palette (jump to a pane, run the demo job, submit), **⌘1…⌘0** switch panes, and clicking an underlined term such as *reserved* explains it. Open a queued job to see why it is waiting. Reservations are bookkeeping, not a GPU meter.

## 6. Let tenants and assistants in safely

- Tenants use `GRYVIA_TENANT_TOKEN`; quotas and GiB-hour budgets are per tenant.
- Owner-aware Macs: set a Mac's policy to *only when I am away* in the Fleet view.
- `mcp/gryvia_mcp.py` lets an assistant read fleet state (writes need `--allow-write`).
- `make deploy`/`make verify` run the full test and build; see [TESTING.md](TESTING.md).

## When something is wrong

| Symptom | Check |
|---|---|
| `doctor` says unreachable | server running? `GRYVIA_SERVER` points at it? |
| Deploy stays queued | `gryvia nodes`: online, not drained, enough free GiB, artifact on that Mac |
| Request returns 503 `no allowlisted inference replica` | model not deployed, evicted, or its Mac is offline |
| Request returns 502 | the replica failed; with replicas the gateway already tried one other |
| Gatekeeper blocks the app | the v0.4.0 DMG is notarized; for ad hoc or unsigned builds Control-click → Open |

## Honest limits

One GPU per Mac; GPU utilisation is device-wide, not per job; reservations are bookkeeping; energy is an estimate; runtimes are not sandboxed, so only enrol Macs you would let an admin run code on. See [SECURITY.md](../SECURITY.md).
