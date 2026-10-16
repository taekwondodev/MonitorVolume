# Project Instructions

## Verification

Use the repository command surface:

- `make test` runs the Mac Swift test suite, the `Shared/MonitorRemoteProtocol` package tests, and the iOS companion tests on an iOS 26 or later simulator.
- `make check` runs the strict-concurrency Release builds for macOS and the unsigned iOS simulator, and the tooling checks.
- `make build` builds, signs with an Apple Development identity when available (otherwise ad hoc), installs, and launches `~/Applications/Monitor Volume.app`. The Accessibility and Local Network grants survive rebuilds with the stable Apple Development identity; ad hoc builds may require both again after each rebuild. The first build after an identifier change requires the grants again.
- `make ios-ipa` builds the unsigned companion `.build/ios/MonitorRemote.ipa` for SideStore.
- `make verify` verifies the installed bundle and exact live process.
- `make profile` measures the installed Release app at idle and regenerates the committed chart.
- `make clean` removes only SwiftPM build artifacts.

## Remote input

Read [ADR 0007](docs/adr/0007-remote-input-as-synthetic-media-keys.md) before changing the companion listener, its wire protocol, or how remote input reaches the event tap, and before adding authentication or a second input path.

## Dev cycle

### Issue tracker

Issues, specs, and tickets live in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Issue labels

Triage uses `needs-grilling` and `ready-for-agent`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.
