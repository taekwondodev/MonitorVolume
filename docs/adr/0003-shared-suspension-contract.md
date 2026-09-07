# ADR 0003: Shared suspension contract and offline conformance drive

- Status: Accepted
- Date: 2026-09-07
- Tracking issue: [#29](https://github.com/taekwondodev/ProArtVolume/issues/29)
- Parent design: [#28](https://github.com/taekwondodev/ProArtVolume/issues/28)

## Context

The media-key tap can lose permission or be disabled by the system/user while work is queued or a command is in flight. Recreating a tap from the disabled callback is not an acceptable recovery policy: it can churn ownership, replay input, and leave the system input path in an unknown state. Candidate tap topologies must therefore share one lifecycle and admission contract before either topology is implemented.

The repository's DDC Service already owns serialized hardware work and read-only recovery. The shared contract must not duplicate that state machine in a benchmark-only language model. It must drive the Swift Domain and Service seams with controlled monitor/audio ports, while keeping CoreGraphics, AppKit, Accessibility, Launch Services, and physical DDC proof outside the offline claim.

## Decision

`ControlEligibility` in `ProArtVolumeCore` is the common synchronous gate. It owns an exhaustive lifecycle phase, generation, session-bound delivery, consumed key-down pairing, bounded FIFO admission, and admission metrics. Its mutex covers only memory bookkeeping; framework callbacks and async I/O never run under the lock.

The lifecycle rules are:

- Missing/revoked permission, either tap-disabled signal, tap creation failure, and delivery overflow latch suspension. Suspension invalidates the session, discards queued delivery, rejects later downs, and remains latched until `reopen`.
- `reopen` begins a new validation generation only after the previous owner calls `releaseTap`. It never waits for a callback or the MainActor. A key-up paired with an admitted down remains consumable until tap release.
- Permission polling is an active-lifecycle policy, outside callbacks, at the declared approximately one-second cadence. It stops in suspension and sleep. A permission regrant, output change, reconnect, hardware recovery, or stale result cannot publish through a suspended gate.
- Sleep invalidates pending work. Wake requests fresh validation only for a lifecycle that slept while active; a suspended lifecycle remains suspended. The Service must read current output and hardware state before publishing a new session.
- DDC failures remain temporary Service unavailability with the existing backoff. Recovery never restores input eligibility by itself, replays a failed command, or cancels a transport call that already started.
- Admission is finite and non-blocking. With the frozen offline fixture capacity of two, a third held down returns `passThroughAfterOverflow`, latches suspension, and discards pending delivery.

`Sources/ProArtVolumeOfflineHarness` is the shared Swift conformance runner. It exercises intent boundaries, one ordered consumer, Service writes, read-only recovery after failed reads and writes, suspension/reopen, sleep/wake, overflow, stale delivery, and tap teardown with controlled ports. It is deliberately not wired as a new production tap owner in this ticket.

The existing `MediaKeyInterceptor`/`ApplicationCoordinator` adapter remains the pre-candidate integration surface; its automatic tap-recreation behavior is not claimed as resolved by this offline contract. Candidate Handler integration and native runtime proof are follow-up work under the later runtime campaign.

`scripts/offline_comparison.py` builds the Release harness, runs the same executable in full-instrumentation and instrumentation-none modes, samples the harness process at 20ms with `ps`, validates CPU normalization, resident-set-size reporting (baseline is the last sample in the 0–200ms active-idle window; peak is the maximum observed RSS), and monotonic nonnegative process-uptime event timestamps without introducing a callback-duration SLA, and binds every report to the resolved executable artifact and SHA-256. Published report paths are repository-relative. The declared matrix is full-active, none-active, and full-suspended. The protocol is descriptive: it has no product latency SLA and must not be called installed-app performance.

## Evidence boundary

The offline report must state these framework measurements as unavailable or modeled until a later runtime campaign provides direct evidence:

- CoreGraphics event timestamp to callback entry and callback duration;
- native tap creation, disable, teardown, and system-input effects;
- Accessibility identity, native prompt visibility, and permission regrant behavior;
- AppKit OSD first draw and physical scanout;
- physical DDC transport and monitor restoration;
- native wakeup and resource counters.

The report does include a live-readiness list, controlled Service outcome, admission occupancy/wait metrics, process CPU/RAM windows, descriptive full-versus-none CPU/RAM deltas, instrumentation-overhead pair, and repeatability/comparison procedure. It records rejected and discarded work instead of treating a successful executable run as native framework proof.

## Corrected incident record

The raw revoke/regrant capture remains at `.hermes/verification/evidence/revoke-granted/revoke-incident-captured.log` and is not rewritten by this contract. Its four timeout signals occur on the same recreated tap after regrant; the capture contains no subsequent tap creation, enable, source removal, or invalidation during those timeout cycles. This records that repeated tap recreation was not observed in the incident evidence. Historical acceptance marks remain lifecycle observations, not callback-entry or native timing measurements.

## Consequences

Both future candidates consume the same typed lifecycle and report contract. A candidate may add a framework adapter or measurement adapter, but it may not introduce a second suspension boolean set, unbounded callback queue, automatic tap recreation, input reinjection, or benchmark-only policy model. Candidate-specific runtime evidence remains a separate, user-authorized verification step.

`make offline-contract` is the repository entry point. `make test`, `make check`, and `git diff --check` remain required code-delivery gates. Offline evidence is non-invasive: it does not install or launch the app bundle, change Accessibility permissions, synthesize system input, or touch the physical monitor.
