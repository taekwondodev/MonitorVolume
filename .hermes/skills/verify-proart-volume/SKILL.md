---
name: verify-proart-volume
description: Use when verifying ProArt Volume's macOS menu-bar bundle launch and runtime presence.
---

# Verify ProArt Volume

Verify the real macOS application bundle through Launch Services. The helper owns an isolated ad-hoc signed bundle, one exact process, scratch state, and durable JSON evidence.

## Quick proof

Run from the repository root:

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py prove
```

A pass requires `status: passed`, a surviving evidence path, and no remaining owned process.

## Launch

Prepare an isolated Release bundle:

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py prepare
```

The JSON response contains `state`. Preserve that path for the following commands. Preparation builds with strict concurrency, assembles `ProArt Volume.app`, writes its agent-only plist, and applies an ad-hoc signature.

## Doctor

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py doctor --state <state-path>
```

Doctor verifies the intended repository, bundle structure, `LSUIElement`, executable path, and code signature. It is read-only.

## Drive

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py drive --state <state-path>
```

Drive opens the prepared bundle through Launch Services, resolves the process by its exact executable path, checks that it remains alive, and writes the launch evidence named in the response.

## Evidence

Evidence lives under `.hermes/verification/evidence/<run-id>/launch.json`. It records the bundle identity, executable, PID, process command, launch method, liveness checks, and pass condition. A launch passes only when the process remains alive and its command identifies the exact prepared bundle.

## Cleanup

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py cleanup --state <state-path>
```

Cleanup signals only the PID whose current command still contains the exact owned executable path. It removes run scratch state and preserves evidence. `prove` performs cleanup even after a failed drive.

## Isolation

Build, bundle, state, and identifier are unique per run. Parallel builds and launches are safe. Launch Services and the macOS user session remain shared platform resources, so visual menu-bar drives must run serially until a dedicated UI harness exists.

## Capability map

Read `references/features/README.md` before claiming coverage. Only bundle launch is currently automated. Icon and popover presentation remain explicit visual gaps.
