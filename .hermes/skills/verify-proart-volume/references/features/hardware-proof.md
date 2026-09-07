# Hardware transition and restoration proof

## Explicit drive

Run `python3 .hermes/skills/verify-proart-volume/scripts/verify.py prove` only when changing monitor volume and mute briefly is acceptable. Ordinary `make verify` never invokes this drive.

The driver builds and verifies the installed app, stops its exact process, then invokes the Release probe through `scripts/probe-monitor-status.sh`. The probe composes `HardwareProofService` with real adapters. A file lock excludes simultaneous tooling proof invocations. Keep other app launches, builds, direct probes, and monitor-control tools stopped for the entire run; the lock is not a system-wide hardware lease and cannot prevent an external launch.

## Pass condition

Trusted initial state precedes all writes. Volume changes by one point, except 100 changes to 99, then exactly one Service restoration command is attempted. Mute inverts and restores under the same rule. Every real transition and restoration must have matching observed state. An unconfirmed restoration stops later writes. A failed transition remains a failed phase even if restoration succeeds.

The report distinguishes `writeAttempted` from an eligibility refusal, carries per-phase relative timing, and captures final state or a read error. The Python consumer validates values and ordering instead of trusting a status string. It records installed-app and probe executable hashes separately; probe evidence is not evidence that media-key handling or OSD rendering worked.

## Evidence and cleanup

The wrapper persists raw stdout, stderr, exit code, structured report or parsing/validation failure in `.hermes/verification/evidence/hardware-*.json`. The driver persists each stage in `<run-id>/launch.json` before cleanup. Failed evidence survives. Exact-path cleanup uses repository tooling and leaves the installed bundle intact. Never deliberately induce restoration failure on the physical monitor.

Deterministic Service and tooling tests cover safe failure seams. Physical transitions, restoration, and exact-process cleanup require the live drive and cannot be inferred from those fixtures.
