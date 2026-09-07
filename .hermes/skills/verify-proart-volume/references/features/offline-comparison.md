# Offline shared-contract comparison

## Public entry point

Run `make offline-contract` from the repository root. The command builds the `ProArtVolumeOfflineHarness` Release executable with strict concurrency, then runs the declared non-invasive matrix: full instrumentation/active workload, instrumentation-none/active workload, and full instrumentation/suspended workload.

## What it proves

The Swift harness drives the shared `ProArtVolumeCore` Domain and Service seams with controlled monitor/audio ports. Its report covers:

- latched suspension for permission, tap-disable, creation, and overflow reasons;
- explicit reopen after old-owner tap teardown;
- sleep/wake fencing and fresh Service validation;
- bounded FIFO admission, key pairing, rejection, and discard bookkeeping;
- intent boundary/parity examples and stale-delivery rejection;
- existing DDC read recovery/backoff without replaying commands;
- executable path/SHA-256 binding and declared CPU/RAM sampling windows.

The parent samples process `%CPU` and resident-set-size RSS in KiB with `ps` every 20ms. CPU is normalized by logical CPU count; RAM baseline is the last sample in the 0–200ms active-idle window and peak is the maximum observed RSS. Event timestamps are accepted only when monotonic and nonnegative process-uptime values; no callback-duration SLA is defined. Wakeup/resource counters and native tap/thread timing are explicitly unavailable or modeled.

The parent runner validates the JSON, records descriptive full-versus-none CPU/RAM deltas without a product SLA, and persists raw stdout, stderr, per-run reports, and the comparison report under the stable ignored directory `.hermes/verification/evidence/offline-contract/`. Published JSON uses repository-relative artifact/evidence paths.

## What it does not prove

The offline drive never installs or launches the app bundle, changes Accessibility permissions, synthesizes system input, invokes CoreGraphics event taps, presents AppKit UI, or writes a physical monitor. Therefore it cannot prove native event-to-callback timing, tap teardown effects on system input, permission-prompt visibility, OSD draw/scanout, physical DDC transitions, native wakeups/resources, or installed-app performance. Each report names those gaps explicitly.

The resource values describe the harness process only. They are not product limits, latency SLAs, or a substitute for the later user-authorized runtime campaign.
