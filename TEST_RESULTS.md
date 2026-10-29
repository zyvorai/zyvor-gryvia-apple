# Delivery verification — 14 October 2026

Environment: Linux container, Python 3.12.14, Node 24.19.0. No Swift compiler or Apple GPU available.

| Check | Result |
|---|---|
| Python unittest suite | 54 tests pass |
| Python compilation: server, scripts, runtime wrappers | Pass |
| `node --check web/app.js` | Pass |
| Shell script syntax | Pass |
| Swift compilation / XCTest | Not run: Swift toolchain absent |
| Native Mac agent end-to-end smoke | Not run: requires macOS; script and CI supplied |
| Metal, MLX, llama.cpp, MPS, Core ML execution | Not run: no Mac/GPU/runtime dependencies |
| Browser interactions and screenshots | Not run: Chromium unavailable; browser download returned an invalid/truncated archive |
| GitHub Actions | Dedicated workflow supplied; remote run status must be checked on the PR |

Eight new regression tests cover server deadline signalling, reservation holding, bounded timeout grace, retry deadlines, event deduplication, ordered atomic log batches, stale-attempt rejection and HTTP role enforcement. Four Swift buffer tests are supplied but unrun.

Tests include atomic concurrent claims, priority and fairness ordering, memory and tenant admission, node/runtime selectors, drain, stale-node/thermal/pressure gates, cancellation acknowledgement, retry exhaustion, stale-attempt completion/log rejection, restart persistence, allocation metering, server roles, tenant ownership and log visibility, actual HTTP inference forwarding to a mock worker, token non-forwarding, inference request/concurrency bounds, HTML IDs/assets/panels and absence of credential persistence.

A mock inference response and the CPU demo validate plumbing only. They are not measurements of GPU throughput, performance, isolation or production readiness. The included GitHub macOS workflow builds Swift and runs the CPU subprocess smoke; GPU acceptance must still run on your actual Macs.

This continuation reapplied the prior scheduler patch to main at `4f6fdd1606591f6ab1c561f143cbf02b292a787f`. The Go operator race/vet results were recorded by the previous delivery; Go is unavailable here, so those results were not independently rerun. A browser attempt failed because the Chromium executable is missing. GitHub branch creation through the Zyvor connection returned HTTP 403; no remote branch, PR or CI run was created.

## Verified 2026-10-14 (macOS 27.2 dev Mac, macOS 27.0 Mac mini, Swift 6.4, Python 3.14)

| Check | Dev Mac | Mac mini |
|---|---|---|
| Python unit tests (59) | pass | pass |
| XCTest (21) | pass | not run: needs Xcode (Command Line Tools only) |
| `swift build -c release` | pass (agent + SwiftUI app) | pass (`gryvia-agent` only; SwiftUI macros need Xcode) |
| `mac-smoke.sh` native agent → API → subprocess → logs → completion | not re-run | pass |
| Playwright dashboard test | pass | not run |
| launchd server + agent, `doctor`, `submit --wait` | n/a | pass |

Still unmeasured: Metal/MLX/llama runtimes (only the demo runtime was executed), GPU throughput and isolation.

## Branding + features round (2026-10-14)
Accent `#0088ff` (shared tokens), BUSL-1.1, new Z icon, web dashboard v2 (palette, demo mode, timeline, alerts, templates, bulk, export, settings), `/metrics`, `/api/history`, `/api/priority`, job labels, CLI `top`/`nodes`/`jobs`/`priority`/`metrics`, SwiftUI Settings/menu-bar/Dock badge. Not implemented (deliberately): webhooks and SSE streaming, which need a security review of outbound requests and long-lived connections.

## M0 + M1: GPU detection and live scheduling (2026-10-14)
- Agent reads `AGXAccelerator` from the IORegistry (no sudo): GPU model, **GPU core count**, device/renderer/tiler utilisation, GPU memory in use, CPU P/E cores. Verified against `ioreg` on both Macs: this Mac M4 = 8 GPU cores, the mini = 12 GPU cores; the mini's in-use memory (138.9 MiB) matched the registry value.
- One GPU per Apple Silicon Mac, so "GPUs" = online Macs; utilisation is device-wide (includes other apps), not per job.
- Server: `node_telemetry` ring, `decisions` ring (queue/wait/admit/finish/cancel with reasons), `finished` timestamps, `GET /api/telemetry`, SSE `GET /api/stream`.
- Web: **Live** view (GPU core grid, measured utilisation sparkline, per-job memory reservation vs measured in-use, animated queue → admission → Mac flow, decision feed), streaming with polling fallback, SF system font stack, simulated demo GPUs.
- Native: Live section with Swift Charts, animated lanes; Tenants icon, metric cards, footer fixed.
- Not yet done: M2 (model onboarding/eval/benchmark) and M3 (training, datasets, workflows, deployments).

## M2: Model hub (2026-10-14)
- Server: model registry v2 (status onboarding → ready/failed, path, sha256, size, quant, paramsB, parent), `POST /api/models/onboard` (HF repo/URL, host allowlist, traversal-safe repo/file checks), job kinds `download|benchmark|evaluate|quantize`, `results` and `suites` tables, results parsed from a structured `{"kind":"result"}` log line, quantise creates a child model.
- Runtimes: `hf_download.py` (https + huggingface.co/hf.co only, size cap, SHA-256, auth header never forwarded off-host), `llama_bench.py`, `eval_suite.py`, `quantize.py`, all confined to the managed models directory.
- On the Mac mini (real, not simulated): `onboard` downloaded `ggml-org/tiny-llamas/stories260K.gguf` (1.19 MB, SHA-256 recorded) → `bench` measured 79,929 tok/s prompt / 1,905 tok/s generation → `eval` ran 2 cases through llama.cpp, 2/2 passed. This is a toy 260K-parameter model used only to prove the pipeline; those throughput numbers say nothing about real models.
- MLX + mlx-lm installed on the mini by `make mini-setup` (default device: GPU). No MLX model was run yet.
- UI: Model hub (cards with status/tok/s/eval, onboarding wizard with memory estimate, details + history, evaluate dialog with saved suites, quantise, compare), Playground (needs a registered inference replica), CLI `models/onboard/bench/eval/results`, native Model hub section.
- Not done: streaming Playground (gateway is non-streaming), eval suites larger than the 4 KB inline limit through the UI, LoRA training (M3).

## M3: training, datasets, workflows, deployments, budgets (2026-10-14)
- Server: datasets registry (+ HF download via the `download` runtime), `run_metrics` ingested from structured log lines, job dependencies (`after`, cancelled when a dependency fails), `{{model.path}}`/`{{dataset.path}}` placeholders resolved at claim time, workflows (chain/DAG), LoRA adapter registered as a child model with lineage, serve jobs register/clear a loopback endpoint, tenant GiB-hour budgets with alerts at 80%.
- Gateway: loopback replicas allowed only with `--inference-loopback` (set by `install-server.py`), still no redirects and no forwarded platform token.
- On the Mac mini (real runs): MLX LoRA fine-tune of `mlx-community/SmolLM-135M-Instruct-4bit` on a 24-row toy FAQ dataset, 40 iterations, validation loss 5.33 → 3.84, adapter registered as a child model; `llama-server` deployment of the 1 MB test model answered a chat request through `/v1/chat/completions` (output is toy-model babble) and `undeploy` cleared the endpoint.
- Bugs caught by real runs: mlx-lm's table output was not parsed (fixed, ANSI-safe parser + test); stale endpoints survived cancellation (fixed: cancelled/expired serve jobs clear them, one replica per model).
- UI: Build (Model hub, Datasets, Training with live loss chart, Playground), Run (Workloads, Workflows, Deployments), Govern; CLI `datasets`, `dataset-add`, `train`, `metrics-run`, `deploy`, `undeploy`; native Model hub gained Deploy and a datasets list.
- Not done / limits: single-Mac, single-GPU training only; Playground is non-streaming; a loopback replica is only reachable from the Mac running the control plane; training numbers here come from a 135M toy model and a 24-row dataset and say nothing about real fine-tuning quality or speed.

## Real 1B benchmark (2026-10-14, Mac mini "Apple M6", 12 GPU cores, 16 GiB)
`bartowski/Llama-3.2-1B-Instruct-GGUF` · `Llama-3.2-1B-Instruct-Q4_K_M.gguf` · 807,694,464 bytes · SHA-256 `6f85a640…11df83`, onboarded through Gryvia (HF download, 0.8 GB).
- llama-bench (Homebrew llama.cpp, 512 prompt / 128 generated tokens, 3 repetitions): **5,999 tok/s prompt, 151.3 tok/s generation**.
- 5-case factual prompt suite (greedy decoding): **5/5 passed**, 0.7–2.0 s per case.
- Gryvia's memory estimate for the model: 1.5 GiB. Single run on an otherwise idle Mac; not a statistical benchmark.

## Real LoRA fine-tune of a 1B model (2026-10-14, Mac mini, Apple M6 / 12 GPU cores / 16 GiB)
`mlx-community/Llama-3.2-1B-Instruct-4bit` · 75-row synthetic Gryvia FAQ (15 facts × 5 phrasings, written for this test) · 150 iterations, batch 2, 8 LoRA layers, lr 5e-5, run as a Gryvia `train` job.
- Train loss 4.615 → 0.137; validation loss 5.63 → 0.132. The validation rows come from the same 15 facts, so this measures memorisation of the FAQ, **not** generalisation.
- Throughput (median over reports): ~939 tokens/s training.
- Adapter registered as `mlx-community__Llama-3.2-1B-Instruct-4bit-lora-9199db` with lineage to the base model.
- Spot check (mlx_lm generate, greedy): base model answered "What does drain do?" with plumbing; the adapter answered with the Gryvia definition. It also answered an unrelated MLX question with a Gryvia-flavoured wrong explanation, i.e. the small dataset leaks into out-of-domain answers.
- Fixed in the same session: `llama_serve.py` now exits if its parent agent goes away (an agent restart had left an orphan llama-server).

## Adapter evaluation, fuse and deploy (2026-10-14, Mac mini)
- Eval runtime gained `--engine mlx [--adapter DIR]`; evaluated inside Gryvia on a 4-case FAQ suite: **base model 1/4, LoRA adapter 4/4** (the France control case passes in both). Same caveat as before: the cases are phrased like the training facts.
- New `fuse` job (mlx_lm fuse → `models/_fused/<adapter>`) registers `<adapter>-fused` as a standalone MLX model; `serve --engine mlx` runs it with `mlx_lm.server` and the gateway routes to it (`workerModel=default_model`).
- Through the gateway the fused model answered "What is a tenant?" with the Gryvia definition and "capital of France" correctly, but answered "What does drain do?" with a generic plumbing answer: training used raw `Q:/A:` text while the chat endpoint applies the chat template. Train on chat-formatted rows if you intend to serve through chat.
- Bugs caught by these runs: adapter folder was outside the confined models directory (now `state/runs` is an allowed managed root); mlx_lm.server needed `model: default_model`.

## Held-out fine-tune experiment (2026-10-14, Mac mini, Llama-3.2-1B-Instruct-4bit)
Setup: 8 Gryvia facts × 5 training phrasings = 40 rows, 150 iterations, batch 2, 8 LoRA layers, lr 5e-5, identical for both adapters; only the row format differs (raw `Q:/A:` text vs chat `messages`). Evaluated inside Gryvia with `eval --remote-cases` on 24 **unseen phrasings** (3 per fact, plain user questions) plus 4 general-knowledge controls. Keyword-containment scoring (strict: a correct paraphrase can miss the key phrase).

| Model | Held-out phrasings | Controls |
|---|---|---|
| base | 0 / 24 | 4 / 4 |
| adapter, raw-text rows | 18 / 24 | 4 / 4 |
| adapter, chat-format rows | 20 / 24 | 3 / 4 |

- The chat adapter's failures: two answers borrowed another fact's text (cross-contamination), one on-topic paraphrase missed the key phrase, one hallucinated what the Training page does, and one control regressed ("Red Planet" → Mercury, i.e. some forgetting).
- n is tiny (24 + 4); the 18 vs 20 difference is not significant. Takeaway: both adapters generalise to new wordings of seen facts; chat format helps a little for chat-style use but did not remove contamination or forgetting.
- Bugs found and fixed while running it: the agent deadlocked in `Process.waitUntilExit()` after a child exited, leaving the job unfinished and the Mac offline (now polls `isRunning`); large eval result lines were truncated by the 2,000-character log cap (the wrapper now emits one `case` line per case and the server assembles them).

## Larger held-out fine-tune: facts-only vs facts + self-rehearsal (2026-10-14, Mac mini, Llama-3.2-1B-Instruct-4bit)
Data: 24 Gryvia facts × 5 question stems = 120 chat-format rows; held-out = the same 24 facts asked with 3 **unseen stems** (72 prompts) plus 24 general-knowledge controls. The "rehearsal" variant adds 60 general Q&A rows answered by the *base model itself* (self-distillation) to preserve its behaviour. Both: 120 iterations, batch 2, 8 LoRA layers, lr 3e-5. Scoring is keyword containment, which is strict (e.g. "three" does not match "3").

| Model | Held-out phrasings | Controls | Final val loss |
|---|---|---|---|
| base | 3 / 72 | 23 / 24 | – |
| adapter, facts only | **71 / 72** | 20 / 24 | 0.117 |
| adapter, facts + rehearsal | 65 / 72 | **23 / 24** | 0.178 |

- Facts-only: 2 of its 4 control misses are scoring artifacts ("seven continents", "three sides"); 2 are real regressions ("Romeo and Juliet" with no author, "7 times 8" answered with an instruction instead of 56).
- Rehearsal removed the real regressions (its one control miss, "three sides", is an artifact the base model also hits) at the cost of 6 more missed facts (65 vs 71 of 72). Pick by use case; neither run is statistically strong (n = 72 / 24, one seed).
- Compared with the earlier 8-fact run (18–20/24 held-out, controls 3–4/4) the larger and more varied set generalises to new stems far better, but the stems are templated, so unseen *templates* remain untested.
- Playground now streams (SSE relay with byte/time bounds). Measured on the mini with Llama-3.2-1B Q4_K_M through the gateway: 120 chunks, 0.28 s to first token, 1.07 s total.


## Release engineering and fleet features (2026-10-14, MacBook macOS 27.2 + Mac mini macOS 27.0)
- Packaging: `package-mac.sh` produced DMG, pkg and zip (ad hoc signed, unsigned pkg, not notarized); checksums verify; pkg payload contains the app, agent helper and icon; `package-release.sh` produced server and SDK tarballs, a CycloneDX SBOM and `SHA256SUMS` with no local state inside (asserted by a test). Version is single-sourced from `VERSION` (`set-version.py --check`). Not verified: install of the pkg on a second Mac, Developer ID signing/notarization, the release workflow on GitHub, the Homebrew cask.
- Site: `build-site.sh` + `site-check.mjs` (links resolve, no horizontal scroll at 390 px, light/dark, demo boots, no console errors) pass locally.
- **Idle harvesting (real, Mac mini):** a 40 s job was running; the owner policy was set to `paused`; the job yielded within seconds (`owner returned`), was requeued at attempt 0 (no retry consumed), stayed queued while paused, started again when the policy returned to `always`, and succeeded. Presence on the mini reported real values (idle 985 s, locked). Not exercised: a keyboard/mouse event on an unlocked desktop, battery rules on a laptop.
- **Provenance (real, Mac mini):** CryptoKit-signed attestations verified by the server's pure-Python Ed25519 (benchmark, inference and a fresh Hugging Face download); the downloaded model carries a verified one-link chain; an older model downloaded before attestation shows none. Not exercised: a fine-tune → fuse chain on hardware (covered by unit tests).
- **Energy:** estimation math and the `powermetrics` plist parser are unit-tested; the helper was **not** run (it needs sudo), so no energy number from real hardware is claimed.
- **MCP:** 8 tests (read-only default, write tools gated and marked, argument validation, tenant scoping, stdio loop). Not run against a real MCP client.


## Web UI and site redesign (2026-10-14, MacBook, Chromium via Playwright)
- Python suite 154 tests, Swift 19 XCTests, browser test (hero number, ring, segmented policy, chart hover tooltip, flow particles, reduced motion, 390 px layout) and `site-check` pass.
- Screenshot matrix: light/dark × flat/glass × 1440/390 px for Live, Fleet, Timeline and Model hub, reviewed visually; no horizontal overflow in any of the 32 captures.
- Not verified: Safari and Firefox rendering (Chromium only), the native SwiftUI app (unchanged), a long-running live fleet with the new idle sparkline (demo mode only).


## Hyperparameter sweep (2026-10-15, Mac mini macOS 27.0, M6 / 12 GPU cores)
- Control plane and native agent started from a working copy of this branch; MLX + mlx-lm installed into a fresh venv. `gryvia sweep mlx-community/SmolLM-135M-Instruct-4bit --dataset toy --lr 1e-5,1e-4 --layers 4,8 --iters 30 --memory-gib 2` queued 4 ordinary training jobs on a 48-row synthetic arithmetic dataset.
- The Mac ran them one after another (exclusive reservations): starts at +0, +12, +16 and +21 s from submission (the first includes model load), all four succeeded.
- Ranked by final validation loss: lr 1e-4 / 8 layers 0.609 (best), lr 1e-4 / 4 layers 0.618, lr 1e-5 / 8 layers 1.419, lr 1e-5 / 4 layers 2.112. Each run produced a registered LoRA adapter with signed provenance.
- Caveats: a 135 M-parameter model on a toy dataset with 30 iterations, one seed per cell, so the ranking says the larger learning rate learns faster here, nothing about quality; the 0.609 vs 0.618 difference is within noise. The run used one Mac, so fan-out across several Macs is covered by unit tests only.
- The mini was cleaned afterwards (processes stopped, venv and state removed).

## Fleet reliability PR (15 October 2026, Linux review environment)

Changes and usage: [docs/FLEET-RELIABILITY.md](docs/FLEET-RELIABILITY.md).

- Added regression scenarios for artifact locality and staged replicas; live headroom/working-set gates; critical-pressure cancellation; strict chain rechecks; signed-status consistency; JSON and SSE agent relay; lease/node/sequence fencing; bounded queues, timeouts, client close and stale deployment ownership; deterministic, disjoint dataset splits; artifact tamper/symlink rejection; SIGTERM escalation; checkpoint offsets and changed-input refusal; and CLI stage → fit → deploy.
- An actual HTTP controller, a simulated polling agent and a separate mock runtime complete the relay integration scenario. A fake MLX subprocess exercises failed-segment → remaining-step continuation. Neither test measures GPU execution or model quality.
- The native CI fix addresses the observed SwiftUI expression timeout at `Desktop.swift:869`. Native memory-pressure collection and the Swift relay require the supplied macOS build/XCTest/smoke checks. No Swift compiler, macOS or Apple GPU is available in this environment, so these changes have **not been compiled or hardware-validated here**.
- The original process-group test used a fixed delay and `pgrep`; it failed in the untouched baseline in this environment. It now waits for a child-written PID readiness marker and verifies reaping, and an additional test verifies escalation against a child that ignores SIGTERM.
- Definitive command output and pass counts are in the ZIP's `validation/` directory. Earlier entries in this file describe prior work and are not fresh measurements from this PR.
- Final validation for this PR: **192 Python tests passed in 34.822 s** (Python 3.12.14 on Linux). Compilation, JavaScript syntax, source headers, version consistency, shell syntax and `git diff --check` passed. Python 3.14 CI, Swift/XCTest, the new native relay smoke and real GPU/fleet validation remain pending. The final suite emitted no uncaught request-handler tracebacks after shutdown and mock-disconnect handling were corrected.

## Fleet reliability on macOS (15 October 2026, MacBook macOS 27.2 + Mac mini macOS 27.2, Swift 6.4, Python 3.14)

- **MacBook:** `make verify` passed (192 Python tests, 21 XCTest including `MemoryPressureTests`, release build), as did `scripts/mac-smoke.sh` and `scripts/native-relay-smoke.py`. The run found three macOS-only problems that the Linux review could not see, all fixed in PR #11:
  - `MemoryPressure.swift` did not compile under Swift 6.
  - The process-group SIGTERM test failed 15 of 25 runs. Darwin returns EPERM from `killpg(pgid, 0)` once only exited, unreaped members remain.
  - A `/var` vs `/private/var` path assertion failed.
- **Mac mini:** `make deploy` passed. It ran `verify.sh` with full Xcode and XCTest, then `mac-smoke.sh`, installed the launchd server and agent, passed the health check and saw the agent register. On the deployed tree, `native-relay-smoke.py` (JSON + SSE, no token forwarding) also passed, `gryvia.py fit --params-b 8 --quant q4 --context-tokens 4096` returned an estimate, and the logs showed no errors. The node's memory pressure read `unknown` until the first OS pressure event, as documented.
- **Not verified:**
  - GitHub CI for PR #11: the run sat queued and the PR was merged before any job ran.
  - Relay or staging between two physical Macs.
  - Real Metal/MLX/llama.cpp workloads through the relay.
  - Critical-pressure cancellation under real memory pressure.
  - Browser tests (Playwright is not installed on the MacBook).

## Idle eviction and capacity on the mini (16 October 2026, Mac mini macOS 27.2, Python 3.14.8)

- **MacBook:** 199 Python tests passed. The new `tests/test_idle.py` deploys through the serve endpoint log and sends chat and stream requests through the real gateway. Against the original patch it fails 5 of 7 (busy and freshly deployed models were evicted), and it passes on the merged fix.
- **Mac mini:** `make deploy` of `c2ee8a0` passed, including `verify.sh` with XCTest, `mac-smoke.sh`, launchd install, health and agent registration. On the live server:
  - `GET /api/capacity` returned online 1, budget 8 GiB, reserved 0, `reservedPct` 0.
  - `GET /api/models/idle` and `POST /api/models/evict-idle` (30-day window) returned empty, with nothing cancelled.
  - `seconds=abc|nan|-1` and an empty `reason` returned 400.
- **Live eviction of a real model server on the mini:**
  - Onboarded `ggml-org/tiny-llamas/stories260K.gguf` (1.2 MB) and deployed it with `llama-server` behind the agent relay (`agentRelay: true`).
  - Three chat requests through `/v1/chat/completions` returned 200. This is also the first real-model run of the fleet-reliability relay.
  - Straight after the traffic, `evict-idle` with a 10-minute window cancelled nothing.
  - After 75 s with no traffic, `idle?seconds=60` listed only that model at 80 s idle, and `evict-idle` cancelled exactly its serve job.
  - The job reached `cancelled`, the model went back to `ready` with no endpoints, no `llama-server` process was left, reserved GiB returned to 0, and the next chat request got 503 `no allowlisted inference replica`.
- **Not verified:**
  - Eviction of an MLX (`mlx_lm.server`) deployment.
  - Eviction with several concurrent deployments on one Mac.
  - Non-admin 403 on the live server (covered by the unit tests only).
  - GitHub CI: runs for PRs #11–#13 stayed queued, and those PRs merged without a CI result.

## Enrollment (join codes)

- **Verified (unit/integration, one Mac):** `tests/test_enroll.py` covers single use, expiry, node binding, re-enrolment replacing the token, revoke, hashed storage, input validation, the rate limiter, and an enrolled token driving `/api/agent/heartbeat` but not `/api/state`. `tests/test_cli.py` covers `gryvia enroll create|list|revoke`. The Playwright suite creates and revokes a code from the Mac fleet view.
- **Not verified:** `install-agent.py --join` against a real launchd on a second Mac; enrolment over HTTPS with a real certificate; the `python3` on this shell is 3.9, so `tests/test_runtimes` (3.10+ syntax) did not import here.

## Streaming logs, notifications, filters

- **Verified (one Mac):** `GET /api/logs/{id}/stream` (SSE): role checks (agent 403, unknown job 404, bad `after` 400), drain-then-`event: end` for a finished job, resume after a sequence number (`tests/test_api.py`). The Playwright suite asserts the dashboard requests the stream, filters Models/Datasets, and switches the Workloads sort, with no JS errors.
- **Not verified:** a long-running job streamed through a real agent; browser Notification permission prompts and the tab-title badge (need a hidden tab and a real permission grant, not exercised by the suite); sort and filter on the SwiftUI app (not implemented there).

## Placement selectors and faster-Mac preference

- **Verified (simulated nodes, one Mac):** `tests/test_placement.py` covers selector validation, `avoidNodes`, `minGpuCores`, `minBudgetGiB`, the bounded yield (a slower Mac waits exactly 3 polls, then runs the job), immediate claim by the faster Mac, and no yield when the faster Mac is draining or busy, for non-GPU kinds, pinned jobs, similar core counts or unknown core counts.
- **Not verified:** behaviour on two physical Macs with real core counts; the effect on queue latency under load; selectors in the web and SwiftUI submit forms (CLI/API JSON only).

## Claim hot path

- **Measured (dev Mac, Python 3.9, 3000 queued jobs, an idle Mac that can run none):** 17.3 ms → 10.6 ms per `claim` poll after parsing each queued body once and skipping unchanged-reason writes. A Mac with no free slot: ~0.03 ms. The benchmark was a scratch script and is not committed.
- **Verified:** wait reasons stay stable across polls (one `wait` decision, not one per poll) and update when the cause changes; an empty-queue claim returns None; scheduler, placement, replica, fleet-reliability and deadline tests pass.
- **Not verified:** 20+ Macs, Python 3.14, concurrent polls from several agents under load. The "N/2 full-queue scans per second" worry from the review is real but small at 2–5 Macs.

## Mobile layout and accessibility (axe-core 4.10.2)

- **Found by the new check, then fixed:** horizontal page scroll at 390 px on Datasets, Activity and Settings (and Training after visiting other views); light-mode text contrast below 4.5:1 for accent text on its tint, the queued/succeeded/failed badges, decision-feed labels, and the done-step "Run a demo job" button (faded by `opacity`); GPU core grid labelled without a role; scrollable regions that were not keyboard-focusable.
- **Verified (dev Mac, Chromium via Playwright):** 16 views × {1440, 390 px} × {light, dark} report no horizontal scroll and no axe `wcag2a`/`wcag2aa` violations, on fixture data from `tests/browser_server.py`.
- **Not verified:** other accent colours (`brand/tokens.json` lists several; only the default blue was checked); dialogs and drawers that are closed in this walk; states with real error toasts; screen-reader announcements; keyboard order; the SwiftUI app; Safari and Firefox.

## Backup and lost-job reconciliation

- **Verified (one Mac, Python 3.9):** `tests/test_backup.py`: snapshot opens as a working store and passes `integrity_check`, holds jobs and join codes, is 0600 in a 0700 folder, sha256 matches, no `.part` or WAL sidecars left; same-second snapshots never overwrite or reuse a pruned name (two ordering bugs found and fixed while writing this); retention keeps the newest N and never touches other files; `keep` validation; HTTP is admin-only and ignores a client-supplied path; `gryvia backup` CLI. `ReconcileTests` in `tests/test_fleet_reliability.py`: release after the grace period (requeue with retries, fail without), no release inside the grace period, when the agent still holds the job, or when an older agent omits the field; other nodes untouched; bad `activeJobs` rejected. `swift build` passes with the agent change.
- **Not verified:** restoring onto a running fleet; backup of a large database under write load; the Swift agent sending `activeJobs` to a real server (build only, no run); that an orphaned child process is really gone after an agent crash (not addressed: this only releases the server's bookkeeping).

## Mac fleet cards and the inline-style CSP bug

- **Found:** under the control plane's `style-src 'self'`, browsers dropped every inline `style="…"` in injected markup (486 CSP console violations in one session). The Live view's memory bars rendered 0 px wide, and per-core and ring styles were lost. The static demo hid this because GitHub Pages sends no such header; the browser test never read console CSP messages.
- **Fixed:** 25 template sites now use `data-style`, applied via a `MutationObserver` and the CSSOM. The browser suite and the 16-view axe walk fail on any CSP violation; `tests/test_web.py` fails on a new `style="` in a template.
- **Verified (dev Mac, Chromium):** fleet cards show role badge, capacity bar (reserved segment 33% and live marker at 25% in the fixture, checked by width and by screenshot), slots, and a role that follows drain; no CSP violations; axe/mobile check still passes.
- **Not verified:** real fleet data (fixtures have 2 Macs, one job); role for a Mac running mixed job kinds beyond the fixed precedence (serve > train/fuse/quantize > benchmark > running); the SwiftUI fleet view (unchanged); other accent colours.

## SwiftUI: Add a Mac and fleet role chips

- **Verified (dev Mac):** `swift build` and `swift test` pass (existing XCTest suites; nothing new added: the Desktop target is an executable and has no test target). `GryviaDesktop --snapshot` against the Playwright fixture server rendered the Fleet pane and the Add-a-Mac sheet in light and dark; the sheet and the new chips were checked by eye in the light PNGs only (dark PNGs were written but not looked at).
- **Not verified:** the sheet creating, listing and revoking real codes (only its preview state was rendered; the endpoints themselves are covered by `tests/test_enroll.py`); the clipboard copy; VoiceOver reading of the code; the Add-a-Mac flow against an HTTPS control plane; role chip for Macs running mixed job kinds.

## SwiftUI: capacity bar, Model hub filter, VoiceOver values

- **Verified (dev Mac):** `swift build` passes; `GryviaDesktop --snapshot` against the Playwright fixture server rendered the Fleet pane with the capacity bar (fill = 4.0 of 12 GiB reserved, tick = 3.0 GiB in use) in light mode, checked by eye.
- **Not verified:** the Model hub filter (compiled, not exercised: snapshots cannot type into the search field); what VoiceOver actually announces for the bar and rows (labels were written, no screen-reader run); dark-mode PNGs; the decorative icon now hidden from VoiceOver; no new automated Swift tests.

## Two agents on one Mac, and a locking bug it found

- **Verified (dev Mac, Python 3.9, real `gryvia-agent` debug builds, loopback, `demo` runtime):** `scripts/multi-agent-smoke.py` starts a control plane and two Swift agents enrolled through join codes (`agent-a`, `agent-b`), pins one job to each, checks both run at once on their own nodes, then `kill -9`s `agent-b` mid-job and restarts it. Results: the lost job was released with 'lease expired; old worker must stop' after 1.3–1.5 s (lease expiry alone would have taken about 20 s), the other agent's job was untouched and finished, and the restarted agent took new work. The demo job's child process was gone after the agent was killed (no orphan observed for this runtime; not tested for llama/MLX).
- **Bug found by it, shipped in PR #49, fixed here:** `Store.agent_actor` (every request from an agent that enrolled with a join code) read SQLite without `store.lock`. The server shares one connection between handler threads, so that raced with heartbeat writes: 2 of the first 7 runs failed with HTTP 500 `database table is locked` (the agent then fails its job closed), and a unit stress test crashed the interpreter (exit 138, SIGBUS). With the lock: stress test passes 5 of 5, smoke passes 8 of 8 consecutive runs. Agents using static `config.json` tokens never hit this path. The server now logs a traceback (path and stack only, no bodies or tokens) for unexpected 500s, which is how the cause was found.
- **Not verified:** two physical Macs (this is two processes on one Mac: no network between them, one clock, one disk); the relay or model staging between agents; more than two agents; a long soak; Python 3.14; the smoke script is not run by CI.

## Locking audit (follow-up to the agent-auth race)

- **Method:** `GRYVIA_DEBUG_LOCKS=1` wraps the shared SQLite connection and raises on any statement run without `store.lock` held (`LockCheckedConnection`, off by default). The whole suite was run with it on, fixing hits until none remained, then an AST pass listed every `Store` method that touches `self.db` outside `with self.lock` or a transaction closure, and each was checked against its callers.
- **Found and fixed (all pre-existing, none caused a failure in testing):** unlocked reads or writes in `submit` (model provenance check), `verify_chain`, `node_policy`, `sweep` (tenant and base-model checks, and the `sweep.created` event), `cancel_sweep`, `cancel_workflow`, and `last_activity_at`. Each could interleave with another handler thread on the shared connection like the `agent_actor` bug. Seven test helpers that read the database directly now take the lock too.
- **Verified (dev Mac, Python 3.9):** 263 tests with the checker on: 0 violations (the one error is `test_runtimes`, which needs Python 3.10+ to import); `scripts/multi-agent-smoke.py` 3 of 3 with the checker also on in the server process. `make verify`, `scripts/verify.sh` and CI now run the suite with the checker on.
- **Not verified:** code paths no test exercises (the checker only sees what runs); that these fixes remove any observed failure (none was observed; this is hardening); Python 3.14 locally; the checker relies on CPython's private `RLock._is_owned`.

## Orphaned runtime children after an agent is killed

- **Verified (dev Mac, Python 3.9, standalone run of the new test body):** `tests/test_runtimes.py::ParentLossTests` starts a throwaway parent, a wrapper using `_common.ManagedProcess` and a `/bin/sleep 300` child, `kill -9`s the parent, and checks the child is gone within 5 s. It passed in 0.17 s with no leftover process. This is the same `ManagedProcess` that `llama_serve.py` and the other bundled wrappers use.
- **Not verified:** a real `llama-server` or MLX process (no GGUF model on this Mac); the test file itself under the project's Python 3.14 (it does not import on 3.9, CI covers it); executables an administrator configures that do not use `ManagedProcess`; a wrapper that is itself `SIGKILL`ed.


## SwiftUI Workloads sort

- **Verified (dev Mac):** `swift build` succeeds with a sort menu on the Workloads pane (Newest, Oldest, Memory, Priority, State) that has an accessibility label.
- **Not verified:** the picker's runtime behaviour or VoiceOver reading (no UI run or snapshot taken); the CI `native` job only builds and tests.

## SwiftUI Datasets and Alerts filter

- **Verified (dev Mac):** `swift build` succeeds. The toolbar search field now also filters the Datasets list (id, status, Mac) and the Alerts pane (title, detail); a filter with no matches shows "No ... match" instead of the "all clear" state.
- **Not verified:** runtime behaviour (no UI run or snapshot), VoiceOver. There is no Swift test for the filter logic.

## SwiftUI live log streaming

- **Verified (dev Mac):** `swift build` and `swift test` (27 tests) pass, including a new `LogStreamTests` for the SSE line parser (rows, keepalive, `end`, junk). The server side of the stream was already covered by `tests/test_api.py`.
- **Not verified:** `API.followLogs` against a running server (the `URLSession.bytes` path has no test and I did not run the app); the polling fallback after a dropped stream; behaviour across a long job or a lost network.
- **Behaviour:** the job detail starts with an empty log, follows the stream, and polls every 2 s if the stream fails or ends before the server's `end` event.

## SwiftUI notification settings

- **Verified (dev Mac):** `swift build` succeeds. Settings has a Notifications section: job finished/failed (default on, as before), a Mac goes offline (default off), and only when the app is in the background. The offline alert fires on an online-to-offline change, not for a Mac that was already offline at launch.
- **Not verified:** that notifications actually appear (they need an app bundle and the system permission; `swift run` skips them), the toggles' runtime behaviour, and VoiceOver. There is no Swift test for this logic.

## TLS guidance for a private network

- **Verified (dev Mac, loopback, LibreSSL 3.3.6 and Python 3.9):** the certificate recipe in `docs/OPERATIONS.md` produced a certificate the server loaded; a client trusting the CA got `{"status": "ok"}` from `/healthz`, a client without it got `CERTIFICATE_VERIFY_FAILED`, and a TLS 1.1-only client could not connect.
- **Not verified:** `security add-trusted-cert`, the Swift agent or desktop app against a private-CA server, a remote address, renewal, mutual TLS (not implemented).

## Lease fencing after reclaim

- **Verified (dev Mac, Python 3.9, `GRYVIA_DEBUG_LOCKS=1`):** `tests/test_scheduler.py` (30 tests) including a new one: after a lease expires and the job is reclaimed on another Mac, the old worker's renew, complete and log writes, and the old lease presented from the new Mac, are all rejected, the new run keeps going and completes. Lease tokens were already unique per claim, so no code changed; the plan's "epoch fencing" item was judged unnecessary at the database level.
- **Not verified:** the old worker's process actually stopping (a token cannot do that); behaviour across two physical Macs.

## Two-agent smoke test in CI

- **Added:** `.github/workflows/multi-agent-smoke.yml` runs `scripts/multi-agent-smoke.py` on a `macos-15` runner for pushes to `main`, tags `v*` and manual dispatch (not pull requests, to keep PR checks fast). The YAML parses; the job has not run on GitHub when this entry was written (see the line below if it was added after the first run).
- **Not verified:** that the agent builds and the smoke test passes on a GitHub macOS runner; its timing there (the test uses real 20 s lease and sleeps and may be slower or flakier on a shared runner).
