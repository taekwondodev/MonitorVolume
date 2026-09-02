---
name: verify-proart-volume
description: Use when verifying ProArt Volume's macOS menu-bar bundle launch and runtime presence.
---

# Verify ProArt Volume

Verify the installed Release application through the repository-owned build and verification scripts. The helper owns only durable JSON evidence and the exact process launched by the build command.

## Quick proof

Run from the repository root:

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py prove
```

A pass requires `status: passed`, a surviving evidence path, and no remaining owned process. The drive delegates build, bundle assembly, stable metadata, signing, installation, launch, process matching, and verification to `scripts/build-app.sh`, `scripts/verify-installed-app.sh`, and `scripts/stop-app.sh`.

## Evidence

Evidence lives under `.hermes/verification/evidence/<run-id>/launch.json`. It records the repository scripts' machine-readable build and verification results. A launch passes only when the installed bundle has the expected stable identity and valid signature and exactly one process owns its executable path.

## Cleanup

`prove` calls `scripts/stop-app.sh` after a successful launch, including when later verification fails. Repository tooling revalidates the exact executable path before signalling a process. The installed bundle and evidence remain in place.

## Isolation

The installed bundle and macOS user session are shared resources. Run this proof serially and only when replacing and briefly launching `~/Applications/ProArt Volume.app` is acceptable.

## Capability map

Read `references/features/README.md` before claiming coverage. Only bundle launch is currently automated. Icon and popover presentation remain explicit visual gaps.
