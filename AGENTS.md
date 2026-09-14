# Project Instructions

## Verification

Use the repository command surface:

- `make test` runs the Swift test suite.
- `make check` runs the strict-concurrency Release build and tooling checks.
- `make build` builds, signs with the Apple Development identity, installs, and launches `~/Applications/Monitor Volume.app`. The Accessibility grant survives rebuilds because the signing identity is stable. The first build after an identifier change requires the grant again.
- `make verify` verifies the installed bundle and exact live process.
- `make profile` measures the installed Release app at idle and regenerates the committed chart.
- `make clean` removes only SwiftPM build artifacts.

## Dev cycle

### Issue tracker

Issues, specs, and tickets live in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Issue labels

Triage uses `needs-grilling` and `ready-for-agent`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.
