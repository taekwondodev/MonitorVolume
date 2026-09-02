---
name: verify-proart-volume
description: Use when verifying ProArt Volume's bundle, runtime presence, and monitor-status presentation.
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

Evidence lives under `.hermes/verification/evidence/<run-id>/launch.json`. It records the repository scripts' machine-readable build, bundle verification, and shared Service/Repository monitor-status results. A run passes only when the installed bundle has the expected stable identity and valid signature, exactly one process owns its executable path, and the target returns a confirmed bounded status with exact same-value read-back for volume and mute.

## Cleanup

`prove` calls `scripts/stop-app.sh` after a successful launch, including when later verification fails. Repository tooling revalidates the exact executable path before signalling a process. The installed bundle and evidence remain in place.

## Isolation

The installed bundle, PA279CV DDC channel, and macOS user session are shared resources. The monitor-status drive performs real same-value volume and mute writes followed by read-back. Run this proof serially and only when replacing and briefly launching `~/Applications/ProArt Volume.app` and exercising the connected target is acceptable.

## Capability map

Read `references/features/README.md` before claiming coverage. Bundle launch, live Service/Repository status, and same-value hardware command confirmation are automated. Icon, popover controls, and error presentation remain explicit visual gaps.
