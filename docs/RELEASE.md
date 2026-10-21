# Release status and how to cut a release

## v0.4.0 (published 21 October 2026)

https://github.com/zyvorai/zyvor-gryvia-apple/releases/tag/v0.4.0. Folds in the never-published v0.3.0 work plus opt-in auto idle eviction, multi-replica serving and the Idle deployments panel (PR #23).

- **Verified (MacBook, macOS 27.2, Python 3.14):** 223 Python tests; `make verify` including XCTest and the release build, run before the final rebase onto main (the rebase conflict was in `server/inference.py` only, Python tests re-run after it).
- **Not verified:** replicas across two physical Macs; relay-mode replicas beyond the existing single-replica relay tests; the Playwright browser test (not installed on this Mac); GitHub CI for PR #23; the pkg (unsigned, no Developer ID Installer certificate) and the zip (not submitted to the notary service separately); a fresh install on a second Mac.
- **Signing and notarization (verified on the MacBook, macOS 27.2):** `Gryvia-0.4.0.dmg` was signed with the Developer ID Application identity (hardened runtime), accepted by Apple's notary service and stapled. `stapler validate` passes and `spctl` reports "Notarized Developer ID" for the DMG and the app inside it. All three `.sha256` files verified against the files downloaded from the published release.
- **How the assets got there:** the release workflow created the release and tarballs; its Mac job had no signing secrets, so the DMG, pkg and zip (and their checksums) were replaced with the locally built, notarized ones using `gh release upload --clobber`.
- **Homebrew:** the tap is still not created; the cask template carries the 0.4.0 version and checksum.

## v0.3.0 (never published; folded into v0.4.0)

Packaging is implemented and exercised locally; nothing has been published yet.

- **Verified locally (macOS 27.2, Apple silicon, Swift 6.4, Python 3.14):** `scripts/package-mac.sh 0.3.0` produced the DMG, pkg and zip; both `.sha256` files verify; the pkg payload contains the app, the agent helper and the icon; `scripts/package-release.sh` produced the server and SDK tarballs, the SBOM and `SHA256SUMS`; the archives contain no `credentials.env`, `config.json`, databases or caches (asserted by a test).
- **Not verified:** the pkg installed on a second Mac; Developer ID signing and notarization (no credentials available); the Homebrew cask (tap not created); the release workflow on GitHub (not yet run).
- **Signing status of artifacts:** ad hoc signed app, unsigned DMG and pkg, not notarized. Gatekeeper blocks the first launch on other Macs: Control-click → Open, or System Settings → Privacy & Security → Open Anyway. Verify with `shasum -a 256 -c Gryvia-0.3.0.dmg.sha256`.
- **Paid build:** the ₹420 business-use download is a separate Developer ID signed build: `Gryvia-0.3.0.dmg` was accepted by Apple's notary service and has the ticket stapled, so it opens without a Gatekeeper warning. The statement above describes the free builds from the GitHub release and CI, which have no signing secrets. The pkg of the paid build was not checked here.

## Cutting a release

1. `python3 scripts/set-version.py X.Y.Z` (updates `VERSION`, `Info.plist`, `pyproject.toml`, `package.json`, README, About panels) and add `## vX.Y.Z` to `CHANGELOG.md`.
2. `make verify` and `bash scripts/mac-smoke.sh` on a Mac; run `scripts/package-mac.sh X.Y.Z` and `scripts/package-release.sh`.
3. Push the tag `vX.Y.Z`. `.github/workflows/release.yml` builds the archives on Ubuntu, the DMG/pkg/zip on macOS, attests them and creates the GitHub release with notes from the changelog.
4. Download the **published** files, check `shasum -c`, install the pkg on a clean Mac, run `gryvia.py doctor`, and record "Verified / Not verified" here.
5. Update `packaging/homebrew/gryvia.rb` (version, sha256) in the tap.

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
