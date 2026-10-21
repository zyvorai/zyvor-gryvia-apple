# Changelog

## Unreleased

## v0.4.3 — 2026-10-21

- **Mac app**: new app icon (black tile, blue bloom, glowing G); the web dashboard favicon matches.

## v0.4.2 — 2026-10-21

- **Mac app**: clearer About window: a product statement, an honest-numbers line and a shorter licence line.

## v0.4.1 — 2026-10-21

- **Mac app**: a darker, glassier dark theme (black page, blue bloom, glass cards, one surface for sidebar, toolbar and page); hero headers with a ring gauge and utilisation trend on Live, Overview, Fleet, Model hub and Workloads; card layouts for every list pane; About window and a one-time Welcome sheet with an animated queue → admission → Macs illustration; teaching empty states; a job timeline with a plain-language "why it is waiting"; glossary popovers; a command palette (⌘K) and ⌘1…⌘0 pane shortcuts. `GryviaDesktop --snapshot DIR` renders every pane for design review (see `docs/TESTING.md`).
- **Web dashboard**: the same dark look; a Fleet total row on the capacity card; more room above the demo banner.
- **Site**: a Mac app section with screenshots rendered by the app's own snapshot mode against a simulated fleet.
- **Licence**: the Additional Use Grant no longer permits free personal use for versions after v0.4.0; a paid Personal plan (₹420 one-time) is the lowest tier. v0.4.0 and earlier keep the grant they were published under. See `docs/COMMERCIAL-LICENSE.md` (draft, pending counsel review).

## v0.4.0 — 2026-10-21

- **Auto idle eviction (opt-in)**: `autoEvictIdleSeconds` / `--auto-evict-idle` runs the existing transactional idle eviction in the background (off by default, minimum 60 s). Dashboard **Idle deployments** panel on Overview shows capacity and what a window would evict, with a two-click Evict.
- **Multi-replica deployments**: `gryvia deploy MODEL --node A --node B` serves one model from several Macs. Models carry `replicas`; the gateway routes to the least-busy live replica and fails over once before the first byte; one replica ending keeps the model deployed; `undeploy`, **Stop all** and idle eviction stop every replica. Not measured across two physical Macs.
- **Fleet reliability**: outbound agent inference relay (JSON and SSE, lease-fenced and bounded, platform token never forwarded); staged artifact locations with input hashing (`gryvia stage`, `deploy --node`); `gryvia fit` memory advisor; live memory-pressure and headroom admission with critical-pressure cancellation; process-group supervision in the bundled runtimes; seeded, deduplicated LoRA splits with checkpoint continuation (adapter weights only). Fixed on macOS: Swift 6 build of the pressure monitor and EPERM handling in process-group cleanup. See `docs/FLEET-RELIABILITY.md`.
- **Idle deployment eviction (scale-to-zero)**: `GET /api/models/idle?seconds=N` lists deployed models with no gateway request (completed or streamed) and no deployment within the window (0 to 30 days); `POST /api/models/evict-idle` cancels their serve jobs, deciding and cancelling in one transaction. Operator-triggered only; nothing evicts automatically. `GET /api/capacity` returns online nodes and free/reserved GiB; `reservedPct` is reservation bookkeeping, not measured GPU utilisation. Admin only. Tests in `tests/test_idle.py` drive real deployment and gateway paths.
- **Hyperparameter sweeps**: one fine-tune fans out over a small grid (learning rate × LoRA layers × batch size, at most 12 runs) as ordinary queued training jobs; runs are ranked by validation loss with the best marked. Dashboard Sweep panel, `gryvia sweep` / `sweep-status` / `sweep-cancel`, `POST /api/sweeps`, `GET /api/sweeps/<id>`, MCP `gryvia_sweeps`, `gryvia_sweep` and (write) `gryvia_create_sweep`.
- Idle-time harvesting, power/thermal policy and energy estimates, MCP server and App Intents, signed model provenance (in progress for 0.3.0).

### Also included: v0.3.0 (packaged locally, never published)

#### Added
- **Model workbench**: Hugging Face onboarding with SHA-256 and size cap, llama.cpp benchmarks, prompt-suite evaluation (GGUF and MLX/adapters), quantise, compare, streaming Playground.
- **Training and run**: datasets, MLX LoRA fine-tuning with live loss, adapter fusing, workflows with dependencies, llama-server / mlx_lm.server deployments behind the gateway, tenant GiB-hour budgets, Prometheus `/metrics`.
- **Live view**: GPU detection (one GPU per Mac; core count and measured utilisation from the IORegistry), real-time queue → admission → Mac flow, scheduler decision feed, SSE stream.
- **Release engineering**: DMG, pkg and zip (`scripts/package-mac.sh`), server and SDK tarballs, `SHA256SUMS`, CycloneDX SBOM, Homebrew cask template, single-source `VERSION`.
- **Brand and docs**: Zyvor blue tokens, G icon, macOS 27 system fonts, BUSL-1.1 headers, UX contract, security policy.

#### Fixed
- Agent no longer deadlocks in `Process.waitUntilExit()` after a child exits.
- Eval results larger than the 2,000-character log cap are assembled from per-case lines.
- Cancelled or expired deployments clear their endpoint; MLX replicas route with `default_model`.
- Dock tile shows the Gryvia icon independent of the LaunchServices cache.

## v0.2.0

Web dashboard v2 (command palette, demo mode, timeline, alerts, templates, export), native Live/Model hub, CLI tables, `make deploy` to a remote Mac, Python 3.14 / Swift 6.

## v0.1.0 — 2026-10-14

Initial engineering beta: durable scheduling/control-plane API, native Swift worker and SwiftUI app, fleet web console, runtime wrappers, tenant policy, inference routing, allocation metering, launchd deployment and CI.
