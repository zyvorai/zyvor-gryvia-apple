# Gryvia Apple UX contract

Gryvia is an instrument for placing native AI workloads on Macs. It borrows the platform's look so it feels native, and it matches the sibling product Zyvor Vytrix: same blue (`#0088ff`), same concentric radii, same honesty rules.

All colours come from `brand/tokens.json` → `web/tokens.css` and `GryviaCore/Brand.swift` (`scripts/gen-brand.py`). Components use tokens, never raw hex.

## Laws
1. **Colour is data.** The accent (blue by default, eight choices) is for intent: selection, focus, primary actions. Green/amber/red mean job or node state, never decoration.
2. **Say what numbers are.** GiB figures are *reservations* (admission bookkeeping), not measured GPU use. Demo data is labelled "Simulated fleet". Anything not collected is absent, not zero.
3. **Tokens stay out of storage.** The access token lives in tab memory (optionally `sessionStorage` for the tab) and, in the native app, the login Keychain. Preferences (accent, theme, templates) are stored separately and never include it.
4. **Concentric radii.** Window 26 → panels 18 → controls 12 → small 8.
5. **Respect the user.** `prefers-reduced-motion` and `prefers-reduced-transparency` are honoured, plus a manual "Reduce transparency". Focus is always visible (3px accent ring). Every control is reachable by keyboard; ⌘K opens the command palette.
6. **Errors say what to do next.** "Cannot reach the control plane. Is the server running?" beats "Failed to fetch".

## Window styles
`macos27` (default, flat opaque surfaces) and `glass` (translucent sidebar capsule, blur). Light/Dark/Auto. Set in Settings; applied before first paint.

## Layout
Sidebar: **Get started**; **Monitor** (Live, Overview, Mac fleet, Timeline); **Build** (Model hub, Datasets, Training, Playground); **Run** (Workloads, Workflows, Deployments); **Govern** (Tenants, Alerts, Activity, Settings). Mac fleet holds **Add a Mac** (single-use join codes). Job logs stream live (SSE, polling fallback). Workloads sort by priority, memory or state; Mac fleet, Model hub, Datasets and Activity have filters. Desktop notifications are opt-in (Settings), fire only while the tab is hidden, and never contain tokens. Breakpoints 1100px and 767px; no horizontal scroll at 390px.

## Inline styles and the CSP
The control plane serves `style-src 'self'`, so the browser ignores `style="…"` in markup the dashboard injects. Templates write `data-style="…"` instead and `web/app.js` applies it through the CSSOM (allowed by that policy). `tests/test_web.py` fails if a template uses `style="`, and the browser suites fail on any CSP violation in the console.

## Mac fleet cards
Each card shows a role (Serving, Training, Benchmarking, Running, Idle, Draining, Drained, Offline) derived from the jobs the Mac holds, a capacity bar, and the slot count. The bar's coloured segments are admission **reservations** (bookkeeping, not measured use); the dark marker is the GPU memory this agent has allocated; GPU busy is for the **whole device**, not only Gryvia jobs.

## Native app parity
The SwiftUI Fleet pane has **Add a Mac** (toolbar-style button and ⌘K command: creates a single-use join code, shows the install command, copies it, lists and revokes recent codes, notes when a new Mac appears) and a role chip, reserved/budget GiB and a capacity bar on each Mac (the bar's fill is admission reservations, the tick is this agent's GPU allocation; VoiceOver reads both numbers). The toolbar filter now also filters the Model hub. Not yet in the native app: live log streaming, filters on Datasets/Activity, the Workloads sort, and notification settings. `GryviaDesktop --snapshot DIR` renders the sheet with a clearly fake preview code (`DEMO1-DEMO2`).

## Author checklist
Checked automatically (`tests/a11y.cjs`, run by `scripts/browser-test.sh` and CI): every view at 1440 px and 390 px, light and dark, has no horizontal page scroll and no axe-core WCAG 2.x A/AA violation. Not checked automatically: AAA, keyboard-order, screen-reader output, non-default accent colours, the SwiftUI app.

1. Both window styles, light and dark.
2. 390px: nothing cut off.
3. Empty and error states explain themselves.
4. Keyboard: palette, `/`, `r`, `p`, `1`–`9`, `?`.
5. Screenshots come from demo or fixture data only.

## Visual system (v0.3)
- **Type**: system font stack only (SF on Apple platforms; SF Pro cannot be bundled). Sizes come from the ramp `--t-*` in `brand/tokens.json`; display sizes use negative tracking and `text-wrap: balance`; hero numerals are tabular.
- **Materials**: `--mat-thin/regular/thick` blur surfaces, hairline borders, two-layer `--shadow-*`, concentric radii `--r-*`. In-app "Reduce transparency" and `prefers-reduced-transparency` swap materials for opaque fills.
- **Motion**: one spring curve and three durations (`--m-*`). Everything animated is gated by `motionOK()` / `prefers-reduced-motion`; every animated graphic has a static equivalent.
- **Graphics encode data**: hero numbers, GPU ring, heat strip, area charts, flow particles, loss chart, timeline bars and idle sparklines are all drawn from measured state. Idle sparklines cover only the time the page has been open. No decorative data.
- **Contrast**: text and muted text meet WCAG AA in light and dark (checked from `tokens.json`). `forced-colors` has a fallback.
