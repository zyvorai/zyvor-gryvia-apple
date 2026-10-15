# Fleet reliability changes

This change set builds on 0.3.0. It adds controller/agent plumbing and regression scenarios; it is not a claim of GPU isolation or measured fleet throughput.

## Delivered

- Managed serving uses outbound agent polling to relay JSON or SSE from a model server on that Mac's IPv4 loopback. The platform token is never forwarded to the worker. Requests are bounded to 180 seconds, 4 MiB total, 32 KiB per upload, 256 KiB queued response data and 64 pending calls. Polling is sequential per agent. No automatic replay on disconnect/restart.
- Relay operations require the correct authenticated node, active serve job, current lease, unexpired heartbeat and registered endpoint. Cancellation/expiry stops routing. Client close releases admission even before the first chunk. Backpressure rejects excess data rather than buffering without bound.
- Scheduler checks artifact locality, tenant markings, missing managed-path placeholders, OS pressure, estimated live memory headroom and Metal's recommended working set. Critical OS pressure requests cancellation while retaining the reservation through acknowledgement/expiry.
- Native memory pressure uses DispatchSourceMemoryPressure. Free + inactive VM pages provide an **estimate** of reclaimable RAM; 1 GiB is left as headroom. The initial pressure state is `unknown`, not an invented normal reading. This is not a per-process or per-job GPU counter.
- An administrator may stage an identical file/directory on another Mac and register its node-local path. The CLI hashes it; the server compares against the registry; bundled runtimes hash the selected inputs again before model loading. Directory hashes cover a sorted canonical manifest of relative paths, byte lengths and individual file SHA-256 hashes. Symlink entries are refused. Transfers themselves remain operator-managed.
- LoRA validates every row, removes exact canonical duplicates and generates seeded, disjoint train/validation/test splits (normally 80/10/10). Numbered checkpoints determine remaining steps, segments avoid overwriting snapshots, input fingerprints guard checkpoint reuse, and metric steps include the completed offset. Training stays pinned to its first checkpoint Mac after yielding. Resume restores adapter weights only: optimizer and RNG state are not restored.
- Bundled subprocess wrappers terminate process groups, escalate to SIGKILL, reap children, and watch for parent-agent loss. Arbitrary configured executables and abrupt wrapper SIGKILL still require host reconciliation; detached/re-parented descendants are not a supported execution pattern.
- `requireVerifiedChain` optionally enforces a complete signed chain at submission and again at claim. Artifact-producing attestations must contain a signed result digest, and signed success must agree with completion. Download/adapter/fused/quantized outputs carry hashes where produced by the bundled wrappers. This does not establish trust against a compromised worker administrator.
- SwiftUI workload rows/menu are split into smaller expressions to address the type-check timeout observed in main CI. A CPU-only native relay smoke is added to macOS CI.

## Validation status (15 October 2026)

- **Verified on macOS 27.2 (MacBook and Mac mini, Swift 6.4, Python 3.14):**
  - `make verify`: Python suite, XCTest including memory pressure, release build.
  - `mac-smoke.sh` and `native-relay-smoke.py`.
  - A launchd deployment on the mini.
  - Real `llama-server` chat requests through the outbound relay on the mini.
- **Fixed during that validation** (the Linux review could not see these):
  - A Swift 6 concurrency error in `MemoryPressure.swift`.
  - Process-group cleanup exiting 1 instead of 143 on macOS: `killpg(…, 0)` returns EPERM once only exited, unreaped members remain.
  - A `/private/var` path assertion in the tests.
- **Not yet verified:**
  - Relay and staging between two physical Macs.
  - MLX serving through the relay.
  - Critical memory pressure on real hardware.
  - Controller restart and agent termination during a relayed stream.
  - Optimizer/RNG resume, which is not implemented.

Details and commands are in [TEST_RESULTS.md](../TEST_RESULTS.md).

## Usage

Inspect memory fit (replace KV dimensions with the model's actual architecture):

```bash
python3 scripts/gryvia.py fit --model my-model --context-tokens 8192 --concurrency 2 --kv-layers 32 --kv-heads 8 --head-dim 128 --kv-bytes 2
```

Or estimate before onboarding:

```bash
python3 scripts/gryvia.py fit --params-b 8 --quant q4 --context-tokens 4096
```

After copying the complete artifact into a managed directory on Mac B, run **on Mac B** using an administrator credential for your controller:

```bash
python3 scripts/gryvia.py stage model my-model --node mac-b --path /absolute/managed/models/my-model.gguf
python3 scripts/gryvia.py deploy my-model --node mac-b
```

For a dataset, use `stage dataset DATASET_ID --node NODE --path PATH`. Set `GRYVIA_MODELS_DIR` consistently with the agent/runtime if using a non-default root. Credentials remain in the existing environment/Keychain flow. Do not put credentials in job arguments.

The control-plane API additions are `POST /api/fit`, administrator-only `POST /api/artifacts/stage`, and node-bound `POST /api/agent/relay-poll` / `relay-push`. Newly built agents announce relay capability in their managed serve endpoint event. Older agents keep the existing explicitly allowlisted direct-HTTP behavior. Upgrade controller and agent together for the new transport.

Enable the stronger chain gate in the controller config:

```json
{"requireVerifiedChain": true}
```

Merge this key into the existing config; it does not replace its token/origin settings. A signed child of an unattested base remains blocked. Existing adapters without content digests should be regenerated before claiming byte verification.

## Acceptance scenarios

Run the controller/runtime tests on any supported Python host:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check-headers.py
python3 scripts/set-version.py --check
python3 -m compileall -q server scripts runtimes
node --check web/app.js
```

On a Mac with Xcode, additionally run:

```bash
make verify
bash scripts/mac-smoke.sh
python3 scripts/native-relay-smoke.py
```

The last command uses a real Swift agent and a mock local model server, not an MLX benchmark. Before deployment, test real inference with the controller on Mac A and the agent on Mac B; exercise stream disconnect, owner return, critical pressure, controller restart and agent termination. Never induce critical memory pressure on a machine with unsaved work.

## Explicit follow-on work

Operator-triggered idle eviction of deployments now exists (`/api/models/idle`, `/api/models/evict-idle`; see [OPERATIONS.md](OPERATIONS.md#idle-eviction-and-capacity)). Automatic artifact copying/cache eviction, desired-replica reconciliation/autoscaling, rolling replacement and owner-triggered service handoff, durable host-wide orphan reconciliation/epoch fencing, per-job RSS telemetry, full optimizer/RNG checkpoint resume, model-quality promotion gates and distributed MLX gang execution are **not implemented** here. This release still has one managed serve job per model and one execution slot per native agent. MLX tensor/pipeline parallelism, JACCL/RDMA and numerical GPU behavior require separate implementation and physical-fleet qualification.
