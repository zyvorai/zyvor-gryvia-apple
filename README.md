<div align="center">

<img src="brand/gryvia-icon.svg" width="96" alt="Gryvia">

# Gryvia for Apple Silicon

[![verify](https://github.com/zyvorai/zyvor-gryvia-apple/actions/workflows/ci.yml/badge.svg)](https://github.com/zyvorai/zyvor-gryvia-apple/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-BUSL--1.1-0088ff)](LICENSE)
[![Platforms](https://img.shields.io/badge/macOS%2015%2B%20%C2%B7%20Apple%20silicon-000000)](docs/TESTING.md)
[![Python](https://img.shields.io/badge/control%20plane-python%203.14%20%C2%B7%200%20deps-30d158)](server/app.py)
[![Swift](https://img.shields.io/badge/agent%20%26%20app-swift%206-0088ff)](native/Package.swift)

![Gryvia Live view](site/img/live-dark.jpg)

### Your Macs, scheduled.

**A multi-tenant control plane for Apple Silicon fleets.** It admits and places inference, fine-tuning and benchmark jobs against each Mac's unified-memory budget, with quotas, leases, provenance and a live view of every GPU.

**Memory-aware admission** · **Live GPU cores** · **Model workbench** · **Owner-aware** · **Signed provenance** · **Source-available**

🎮 **[Live demo](https://zyvorai.github.io/zyvor-gryvia-apple/demo/)** · 🌐 **[Site](https://zyvorai.github.io/zyvor-gryvia-apple/)** · 🚀 **[Quickstart](#see-it-in-60-seconds)** · 📖 **[Getting started](docs/GETTING-STARTED.md)** · 🔒 **[Security](SECURITY.md)** · 📦 **[Releases](docs/RELEASE.md)** · 🧪 **[Results](TEST_RESULTS.md)**

</div>

> **Zyvor AI Labs · 0.5.0 · BUSL-1.1.** Source-available (not OSI open source); each version converts to Apache-2.0 four years after its first public release. Copyright © 2026 Zyvor AI Labs Private Limited.

## See it in 60 seconds

```bash
alias gryvia='python3 scripts/gryvia.py'               # the CLI ships in this repo
make run-server && make run-agent                      # this Mac joins the fleet
gryvia fit --params-b 8 --quant q4 --context-tokens 4096   # will it fit before I download it?
gryvia onboard my-llama --repo bartowski/Llama-3.2-1B-Instruct-GGUF --file Llama-3.2-1B-Instruct-Q4_K_M.gguf
gryvia deploy my-llama --node mini-01 --node mini-02   # one replica per Mac
curl -s :8443/v1/chat/completions -H "Authorization: Bearer $GRYVIA_TENANT_TOKEN" \
     -d '{"model":"my-llama","messages":[{"role":"user","content":"hi"}]}'
```

Every command is real; the full walkthrough, with what to check when something goes wrong, is in **[Getting started](docs/GETTING-STARTED.md)**. No Mac handy? The **[live demo](https://zyvorai.github.io/zyvor-gryvia-apple/demo/)** runs a simulated fleet in your browser.

## Why Gryvia

| When this happens | Gryvia gives you |
|---|---|
| Three Macs, five jobs, and nobody knows what fits where | **Admission control** against each Mac's unified-memory budget, with priorities, tenant quotas and fairness weights |
| "Is the mini alive, and is it throttling?" | A live fleet view: GPU cores lit by measured utilisation, thermal state, drain and resume, alerts |
| The Mac on someone's desk should not run your 3 am fine-tune while they are working | **Owner policy**: run only when idle, yield instantly when they return, respect battery, Low Power Mode and calls |
| Apps need one endpoint, not a list of Macs | An **OpenAI-style gateway** with streaming, **replicas on several Macs** and one failover before the first byte |
| Models sit on a Mac nobody uses and still hold memory | **Idle eviction**, by hand or opt-in automatic, that frees the reservation (the model stays ready) |
| "Which Mac produced this model, and was it tampered with?" | **Signed provenance**: node-signed attestations, pinned keys, verified chains, an optional deploy gate |
| You want an AI assistant to check or operate the fleet | **MCP server** (read-only by default) and Shortcuts actions |
| You want to try it without hardware | **Demo mode**: a clearly labelled simulated fleet in the browser |

The **[site](https://zyvorai.github.io/zyvor-gryvia-apple/#macapp)** shows the native Mac app in light and dark.

## Who it is for

- **A small AI team with a Mac rack:** several minis and Studios, one queue, quotas so one fine-tune cannot starve the rest, one endpoint for apps.
- **A lab sharing a few machines:** reserve unified memory per job, spot the hot or throttling Mac, keep a signed record of which Mac made which model.
- **One developer, a MacBook and a mini:** the mini does the overnight runs and serves the model; the MacBook stays yours.

## New in 0.4

- **Serve from more than one Mac.** `gryvia deploy MODEL --node A --node B`: least-busy routing, one failover before the first byte, and the model stays up when one replica ends. Not yet measured across two physical Macs.
- **Automatic idle eviction (opt-in).** `autoEvictIdleSeconds` in `config.json`, off by default. An **Idle deployments** panel on the Overview shows what a window would stop.
- **Signed and notarized DMG**, and **`brew install --cask zyvorai/tap/gryvia`**.

## What is in the box

- **Control plane** (`server/`): Python standard library + SQLite, zero dependencies. Priority, fairness, quotas, dependencies, retries, leases, yield-and-resume, model registry, results, provenance, the OpenAI-style gateway with streaming over an outbound agent relay, idle-deployment eviction and a capacity summary, Prometheus `/metrics`.
- **Agent** (`native/Sources/GryviaAgent`): Swift. Reports GPU model, core count and measured utilisation (IORegistry), memory, thermal state, owner presence and power; runs locally configured runtimes; signs attestations.
- **Apps**: web dashboard (`web/`, also the static demo), SwiftUI Mac app with menu-bar pause and Dock badge, CLI (`scripts/gryvia.py`), MCP server (`mcp/`).
- **Runtimes** (`runtimes/`): llama.cpp (bench, evaluate, quantise, serve), MLX (LoRA, fuse, serve, generate), Core ML, Hugging Face download with size cap and SHA-256.

## Install

```bash
brew install --cask zyvorai/tap/gryvia       # signed and notarized DMG, Apple silicon, macOS 15+
# or from source:
make run-server    # control plane; creates ./local with tokens (0600)
make run-agent     # in another terminal: this Mac becomes a worker
```

Enrol another Mac with `make deploy MINI=your-mac` (syncs, builds, tests and installs launchd services over ssh); `python3 scripts/gryvia.py quickstart` tells you what to do next. You can also download the DMG or pkg from the [releases](https://github.com/zyvorai/zyvor-gryvia-apple/releases). The **v0.4.0 DMG is Developer ID signed and notarized**; the pkg and zip are not, and builds made by CI without signing secrets are ad hoc signed. Verify with `shasum -a 256 -c`; for an ad hoc or unsigned build, Control-click → Open.

## Licence and pricing

**Free to read, build and test; paid to run for real work.** The source is under the Business Source License 1.1 (see [LICENSE](LICENSE), the authority; v0.4.0 and earlier keep their original personal-use grant). Each version converts to Apache-2.0 four years after its first public release.

| Plan | Price (GST invoice included) | For |
|---|---|---|
| **Personal** | ₹420 one-time (about US$4.99), [buy](https://payments.cashfree.com/forms/zyvor-gryvia-apple) | one person, no business use |
| **Solo / small team** | ₹4,999 per year (about US$59) | business use, up to 5 Macs |
| **Team** | ₹19,999 per year (about US$239) | business use, up to 25 Macs |
| **Larger fleets** | by quote: sales@zyvor.dev | more than 25 Macs or several entities |

Same Developer ID signed and notarized build for every plan; no redistribution or resale. Terms: [docs/COMMERCIAL-LICENSE.md](docs/COMMERCIAL-LICENSE.md) (draft).

## Honest limits

One GPU per Mac; GPU utilisation is device-wide, not per job; reservations are admission bookkeeping, not isolation; energy is an estimate and needs an optional root helper; training is single-Mac LoRA; there is no sandbox around runtimes, so enrol only Macs you would let an admin run code on. See [SECURITY.md](SECURITY.md) and [TEST_RESULTS.md](TEST_RESULTS.md) for what was measured, on what, and what was not verified. Outbound relay, staged artifacts, memory-pressure admission and the fit advisor are described in [Fleet reliability](docs/FLEET-RELIABILITY.md); relay between two physical Macs is not yet measured.

## Where it fits

Gryvia is not a way to split one model across Macs (see exo and MLX distributed for that). It answers who gets which Mac, when, and within what limits. [docs/COMPARISON.md](docs/COMPARISON.md) has the longer comparison.

## Docs

[Getting started](docs/GETTING-STARTED.md) · [Architecture](docs/ARCHITECTURE.md) · [Operations](docs/OPERATIONS.md) · [UX contract](docs/UX-CONTRACT.md) · [Testing](docs/TESTING.md) · [Release](docs/RELEASE.md) · [Feature matrix](docs/FEATURE_MATRIX.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)
