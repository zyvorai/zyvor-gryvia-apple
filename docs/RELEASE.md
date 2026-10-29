# Release status and how to cut a release

## v0.4.0 (published 21 October 2026)

https://github.com/zyvorai/zyvor-gryvia-apple/releases/tag/v0.4.0. Folds in the never-published v0.3.0 work plus opt-in auto idle eviction, multi-replica serving and the Idle deployments panel (PR #23).

- **Verified (MacBook, macOS 27.2, Python 3.14):** 223 Python tests; `make verify` including XCTest and the release build, run before the final rebase onto main (the rebase conflict was in `server/inference.py` only, Python tests re-run after it). Re-run on `main` after release: `make verify`, `native-relay-smoke.py`, `mac-smoke.sh` (on a spare port, because this Mac's launchd server holds 8443), the Playwright dashboard test (`scripts/browser-test.sh`, Playwright 1.64.1) and `scripts/site-check.mjs` against a fresh site build all pass.
- **Not verified:** replicas across two physical Macs; relay-mode replicas beyond the existing single-replica relay tests; GitHub CI for PR #23; the pkg (unsigned, no Developer ID Installer certificate) and the zip (not submitted to the notary service separately); a fresh install on a second Mac.
- **Signing and notarization (verified on the MacBook, macOS 27.2):** `Gryvia-0.4.0.dmg` was signed with the Developer ID Application identity (hardened runtime), accepted by Apple's notary service and stapled. `stapler validate` passes and `spctl` reports "Notarized Developer ID" for the DMG and the app inside it. All three `.sha256` files verified against the files downloaded from the published release.
- **How the assets got there:** the release workflow created the release and tarballs; its Mac job had no signing secrets, so the DMG, pkg and zip (and their checksums) were replaced with the locally built, notarized ones using `gh release upload --clobber`.
- **Homebrew:** `Casks/gryvia.rb` is in `zyvorai/homebrew-tap` (0.4.0, checksum equal to the `.sha256` file and GitHub's asset digest, `brew style` clean). `brew audit --cask --online --strict zyvorai/tap/gryvia` passes with no offenses, and `brew install --cask zyvorai/tap/gryvia` installed `Gryvia.app` 0.4.0 on the MacBook (macOS 27.2); `spctl` reports "Notarized Developer ID". The installed app has no stapled ticket of its own (only the DMG does), so Gatekeeper checks Apple's records online on first launch.

## v0.5.0 (published 29 October 2026)

https://github.com/zyvorai/zyvor-gryvia-apple/releases/tag/v0.5.0. The small-fleet release (PRs #49 to #66): join-code enrollment, placement selectors, `activeJobs` reconciliation, backups, live logs and notifications, search and sort, mobile and accessibility checks, SwiftUI parity, a lock audit, and a TLS recipe. See `CHANGELOG.md`.

- **Verified (MacBook, macOS 27.2):** `make verify` on the release commit (277 Python tests with `GRYVIA_DEBUG_LOCKS=1`, JS syntax, Swift tests, release build); CI on every PR including #67 (control-plane on Python 3.14, native, site, web); `scripts/multi-agent-smoke.py` (two real agent processes on this Mac, join-code enrollment, kill and restart of one agent) passed 8 of 8 in a loop and 3 of 3 with the lock checker on. `Gryvia-0.5.0.dmg` was signed with the Developer ID Application identity, accepted by Apple's notary service and stapled; after download of the published files the DMG, pkg and zip match their `.sha256` files, `stapler validate` passes and `spctl` reports "Notarized Developer ID" for the DMG. The server tarball matches `SHA256SUMS` and contains no credentials, config or database files.
- **Not verified:** anything on two physical Macs (enrollment, placement, reconcile, kill tests); more than two agents; a long soak; a real `llama-server` or MLX process surviving or dying with the agent; the SwiftUI features at runtime (live log streaming against a server, notifications, sort and filters; only built and unit-tested) and VoiceOver; other accent colours; TLS with the Swift agent against a private CA; the pkg (unsigned) and the zip (not notarized separately); an install of the published pkg on a clean Mac.
- **How the assets got there:** the release workflow created the release and tarballs (its Mac job has no signing secrets); the DMG, pkg and zip and their checksums were rebuilt locally with `scripts/package-mac.sh 0.5.0` (Developer ID signed, notarized) and replaced with `gh release upload --clobber`.
- **Homebrew:** `Casks/gryvia.rb` in `zyvorai/homebrew-tap` still points at 0.4.3 until it is bumped to 0.5.0 with sha256 `7741df8132fec1c0424d03285b7e5ed18a02875f6ec8107350181a9c255f3b09`. `brew style` was clean on the edited file; `brew audit` and `brew upgrade` have not been run for 0.5.0.

## v0.4.3 (published 21 October 2026)

https://github.com/zyvorai/zyvor-gryvia-apple/releases/tag/v0.4.3. New app icon only (PR #44); the web favicon matches.

- **Verified (MacBook, macOS 27.2):** CI on PRs #44 and #45 (control-plane, native, site, web). `Gryvia-0.4.3.dmg` was signed with the Developer ID Application identity, accepted by Apple's notary service and stapled; the published DMG, pkg and zip match their `.sha256` files after download, `stapler validate` passes and `spctl` reports "Notarized Developer ID" for the DMG and the installed app. `brew audit --cask --online --strict zyvorai/tap/gryvia` passes, `brew upgrade --cask` installed 0.4.3, the app launches, and `gryvia.py doctor` passes against the local server. The icon was checked as a render of the `.icns`.
- **Not verified:** the icon in the Dock and the DMG window, and everything listed as not verified under v0.4.1 (live window, shortcuts and palette, Welcome sheet on a fresh profile). The pkg is unsigned and the zip is not notarized separately.

## v0.4.2 (published 21 October 2026)

https://github.com/zyvorai/zyvor-gryvia-apple/releases/tag/v0.4.2. Clearer About window copy only (PR #41).

- **Verified (MacBook, macOS 27.2):** CI on PRs #41 and #42 (control-plane, native, site, web). `Gryvia-0.4.2.dmg` was signed with the Developer ID Application identity, accepted by Apple's notary service and stapled; the published DMG, pkg and zip match their `.sha256` files after download, `stapler validate` passes and `spctl` reports "Notarized Developer ID" for the DMG and the installed app. `brew audit --cask --online --strict zyvorai/tap/gryvia` passes, `brew upgrade --cask` installed 0.4.2, the app launches, and `gryvia.py doctor` passes against the local server.
- **Not verified:** the About window in the installed app (checked only in an offscreen render of the debug build), everything listed as not verified under v0.4.1, the pkg (unsigned) and the zip (not notarized separately).
- **How the assets got there:** same as v0.4.1.

## v0.4.1 (published 21 October 2026)

https://github.com/zyvorai/zyvor-gryvia-apple/releases/tag/v0.4.1. The Mac app and site UX pass (PRs #35 to #38): dark theme, hero headers, teaching empty states, job timeline, glossary, command palette, shortcuts, login-field focus fix.

- **Verified (MacBook, macOS 27.2):** `swift test` (26 tests), release build, the Playwright dashboard test, `scripts/site-check.mjs`, the Python suite (after #35), CI on PR #39 (control-plane, native, site, web), and renders of every pane in light and dark from `GryviaDesktop --snapshot`, viewed one by one. `Gryvia-0.4.1.dmg` was signed with the Developer ID Application identity, accepted by Apple's notary service and stapled; the published DMG, pkg and zip match their `.sha256` files after download, `stapler validate` passes and `spctl` reports "Notarized Developer ID" for the DMG and the installed app. `brew audit --cask --online --strict zyvorai/tap/gryvia` passes; `brew upgrade --cask` installed 0.4.1; the app launches; `scripts/mac-smoke.sh` passes.
- **Not verified:** the real window on screen (screen capture was unavailable), keyboard shortcuts and the command palette in the live app, the Welcome sheet on a fresh profile, the "why it is waiting" box with a real scheduler reason, masked sidebar material on other macOS versions, replicas across two physical Macs, the pkg (unsigned) and the zip (not notarized separately), and a fresh install on a second Mac. The site's Mac screenshots are renders against a simulated fleet.
- **How the assets got there:** same as v0.4.0: the release workflow created the release, then the locally built, notarized DMG, pkg and zip replaced its assets with `gh release upload --clobber`.

## v0.3.0 (never published; folded into v0.4.0)

Packaging is implemented and exercised locally; nothing has been published yet.

- **Verified locally (macOS 27.2, Apple silicon, Swift 6.4, Python 3.14):** `scripts/package-mac.sh 0.3.0` produced the DMG, pkg and zip; both `.sha256` files verify; the pkg payload contains the app, the agent helper and the icon; `scripts/package-release.sh` produced the server and SDK tarballs, the SBOM and `SHA256SUMS`; the archives contain no `credentials.env`, `config.json`, databases or caches (asserted by a test).
- **Not verified:** the pkg installed on a second Mac; Developer ID signing and notarization (no credentials available); the release workflow on GitHub (not yet run).
- **Signing status of artifacts:** ad hoc signed app, unsigned DMG and pkg, not notarized. Gatekeeper blocks the first launch on other Macs: Control-click → Open, or System Settings → Privacy & Security → Open Anyway. Verify with `shasum -a 256 -c Gryvia-0.3.0.dmg.sha256`.
- **Paid build (historical, pre-0.4.0 pricing; the site now lists annual plans, see docs/COMMERCIAL-LICENSE.md):** the ₹420 business-use download is a separate Developer ID signed build: `Gryvia-0.3.0.dmg` was accepted by Apple's notary service and has the ticket stapled, so it opens without a Gatekeeper warning. The statement above describes the free builds from the GitHub release and CI, which have no signing secrets. The pkg of the paid build was not checked here.

## Cutting a release

1. `python3 scripts/set-version.py X.Y.Z` (updates `VERSION`, `Info.plist`, `pyproject.toml`, `package.json`, README, About panels) and add `## vX.Y.Z` to `CHANGELOG.md`.
2. `make verify` and `bash scripts/mac-smoke.sh` on a Mac; run `scripts/package-mac.sh X.Y.Z` and `scripts/package-release.sh`.
3. Push the tag `vX.Y.Z`. `.github/workflows/release.yml` builds the archives on Ubuntu, the DMG/pkg/zip on macOS, attests them and creates the GitHub release with notes from the changelog.
4. Download the **published** files, check `shasum -c`, install the pkg on a clean Mac, run `gryvia.py doctor`, and record "Verified / Not verified" here.
5. Update `packaging/homebrew/gryvia.rb` and `Casks/gryvia.rb` in `zyvorai/homebrew-tap` (version, sha256 from the `.sha256` file).

### Signing and notarization (optional, needs your Apple credentials)

Set repository secrets and the workflow signs automatically; locally export the same variables:

| Variable / secret | Meaning |
|---|---|
| `DEVELOPER_ID_APP` | `Developer ID Application: NAME (TEAMID)`: signs the app, agent and DMG |
| `DEVELOPER_ID_INSTALLER` | `Developer ID Installer: NAME (TEAMID)`: signs the pkg |
| `NOTARY_PROFILE` | profile created with `xcrun notarytool store-credentials` |
| `MACOS_CERTS_P12`, `MACOS_CERTS_PASSWORD`, `NOTARY_KEY_P8`, `NOTARY_KEY_ID`, `NOTARY_ISSUER` | CI-only: certificate bundle and App Store Connect API key |

## Artifacts

| File | What |
|---|---|
| `Gryvia-X.Y.Z.dmg` / `.pkg` / `.zip` | Gryvia.app (SwiftUI app + `gryvia-agent` + control plane under `Contents/Resources/gryvia`) |
| `gryvia-server-X.Y.Z.tar.gz` | control plane only (server, runtimes, web, scripts, docs) |
| `gryvia-sdk-X.Y.Z.tar.gz` | Swift sources to build the agent and app |
| `gryvia-X.Y.Z.cdx.json` | CycloneDX SBOM |
| `SHA256SUMS`, `*.sha256` | checksums |
