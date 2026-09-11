# Project Instructions

## Verification

Use the repository command surface:

- `make test` runs the Swift test suite.
- `make check` runs the strict-concurrency Release build and tooling checks.
- `make build` builds, signs with the Apple Development identity, installs, and launches `~/Applications/ProArt Volume.app`. The Accessibility grant survives rebuilds because the signing identity is stable.
- `make verify` verifies the installed bundle and exact live process.
- `make clean` removes only SwiftPM build artifacts.

## Dev cycle

### Issue tracker

Issues, specs, and tickets live in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Issue labels

Triage uses `needs-grilling` and `ready-for-agent`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.
