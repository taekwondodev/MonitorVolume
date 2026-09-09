# ADR 0003: Shared suspension contract and offline conformance drive

- Status: Accepted
- Date: 2026-09-07
- Tracking issues: [#29](https://github.com/taekwondodev/ProArtVolume/issues/29), [#32](https://github.com/taekwondodev/ProArtVolume/issues/32)
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
- Admission is finite and non-blocking. Candidate conformance and comparative apparatus use the production capacity of eight; a ninth held down returns `passThroughAfterOverflow`, latches suspension, and discards pending delivery.

`ProArtVolumeIssue32Conformance` is the opt-in, candidate-bound Swift runner. Each candidate is compiled in a separate process from its actual `CandidateBinding → MediaKeyInterceptor` post-parse seam. Shared scenario files are byte-identical; topology adaptation is confined to `CandidateBinding`, and observed topology labels are emitted only after the candidate's actual scheduling boundaries execute. The obsolete common `ProArtVolumeOfflineHarness`, which bypassed both candidate bridges, is retired.

The deterministic correctness matrix runs before any apparatus workload. The apparatus then labels active-idle, isolated input, repeated burst, mixed burst, delayed-consumer, suspension, sleep/wake, cleanup, and stress-overflow phases using real `DispatchTime` process-uptime timestamps. It drives only the typed post-parse seam; it does not construct or post CoreGraphics events.

`scripts/issue32_apparatus.py gate` builds and runs exactly one Release candidate. It has no A/B comparison command. The child appends each phase boundary to a synchronized sidecar; the parent observes those records on its own `time.monotonic_ns()` timeline before sampling `proc_pid_rusage`. This avoids comparing unrelated process-local clock epochs while retaining the child's original `DispatchTime` timestamp for audit. Each sample contains instantaneous resident size and cumulative nanosecond user-plus-system CPU time; per-interval CPU utilization is derived from consecutive cumulative values over the parent monotonic interval, never from `ps` lifetime-average `%CPU`. The gate retains every 10ms poll as sampled, failed, or censored raw evidence; requires at least one sample and one wholly-contained CPU interval in every observed phase; reconstructs all total and per-phase summaries from those records; and binds the report to the immutable candidate ref, complete source closure, shared-driver and expected-matrix digests, frozen collection-protocol SHA-256, compiler, retained executable, and executable SHA-256. The collection-protocol digest participates in the configuration digest, and the exact protocol file is retained beside each report. Output directories are caller-selected, must not already exist, and are never cleared. `control --mode repeatability` compares repeated same-candidate behavior fingerprints while deliberately excluding resource and timestamp noise; `control --mode instrumentation` requires full and none modes for the same candidate/workload and verifies behavioral parity. Alternating A/B collection and ranking remain blocked until correctness, evidence-integrity, and same-candidate controls are green under a separately frozen protocol.

`scripts/issue32_collection_protocol.json` is that pre-collection protocol. It freezes one build per candidate, capacity eight, strict Release configuration, full and inactive instrumentation, exact normal and stress phase definitions, 10ms process polling, 40ms phases, one retained warmup and 20 valid measured runs per candidate/workload/instrumentation cell, and a counterbalanced 160-run schedule. It defines per-run timing sample minima, exact input/delivery/admission/rejection/discard accounting, one-core and machine-capacity CPU, resident-memory, missing-data, replacement, equivalence, selection, environment, reporting, and stop rules before any A/B observation exists. Power source, low-power mode, thermal limits, OS/toolchain, and logical CPU count have named observation sources and are retained at block boundaries; a mismatch or unavailable observation stops the block. Equivalence uses a fixed-seed bootstrap interval for paired median B-minus-A differences and the maximum same-candidate median absolute successive difference over at least 19 adjacent differences, rather than an invented latency SLA or a small-sample p95 maximum. Any integrity or correctness failure stops collection; bounded missing numeric data permits at most two preserved replacement pairs before an inconclusive result. `scripts/issue32_collection_protocol.py` validates and materializes the schedule without building or running either candidate.

`scripts/issue32_collector.py` is the only comparative executor. Its default surface validates controls or analyzes an already collected campaign; execution additionally requires the literal `--execute-frozen-campaign` flag, six current source-bound control reports, both exact worktrees, and a new output directory. It builds each candidate once, hashes the source closure before and after the build, and passes the resulting prepared Release executable plus its SHA-256 to every single-candidate apparatus invocation. Every collector-owned subprocess and every apparatus build or lookup command owns a new process group; timeout cleanup terminates that group, waits the frozen grace period, then kills any surviving descendants. During collection the conformance child inherits the apparatus process group, so the collector's outer watchdog covers both processes; the apparatus's inner watchdog still terminates and then kills that direct child. The apparatus refuses any prepared path other than that candidate's Release product and rechecks its hash and source closure on every run. The collector pins the apparatus and expected-matrix digests before preparation and checks both immediately before and after every gate. It retains its own source, apparatus, matrix, protocol, control manifest, candidate binaries, environment observations, all selected and superseded runs, and atomic campaign state. Analysis revalidates every selected report against its recorded digest, candidate/configuration identity, source ref, protocol, apparatus, matrix, child status, scenario/topology contract, raw reconstruction, and behavior fingerprint before deriving metrics. It observes AC power, low-power mode, Foundation thermal state, OS/toolchain/host identity, and logical CPU count before and after each four-run workload block; any drift is terminal. Comparative analysis remains provisional until the post-campaign lifecycle review, so Candidate B cannot be selected by the collector alone.

## Evidence boundary

The offline report must state these framework measurements as unavailable or modeled until a later runtime campaign provides direct evidence:

- CoreGraphics event timestamp to callback entry and callback duration;
- native tap creation, disable, teardown, and system-input effects;
- Accessibility identity, native prompt visibility, and permission regrant behavior;
- AppKit OSD first draw and physical scanout;
- physical DDC transport and monitor restoration;
- native wakeup and resource counters.

The candidate report includes the deterministic scenario matrix, observed topology, named workload phases, typed bridge outcomes, delivery counts, suspension state, and explicit measured/modeled/unavailable observation statuses. The outer gate adds raw process CPU/RAM polls and reconstructable summaries. It records rejected and discarded work instead of treating a successful executable run as native framework proof.

## Corrected incident record

The raw revoke/regrant capture remains at `.hermes/verification/evidence/revoke-granted/revoke-incident-captured.log` and is not rewritten by this contract. Its four timeout signals occur on the same recreated tap after regrant; the capture contains no subsequent tap creation, enable, source removal, or invalidation during those timeout cycles. This records that repeated tap recreation was not observed in the incident evidence. Historical acceptance marks remain lifecycle observations, not callback-entry or native timing measurements.

## Consequences

Both candidates consume the same typed lifecycle and report contract. A candidate may add a framework adapter or measurement adapter, but it may not introduce a second suspension boolean set, unbounded callback queue, automatic tap recreation, input reinjection, or benchmark-only policy model. Candidate-specific runtime evidence remains a separate, user-authorized verification step.

`make offline-contract` is the single-candidate gate entry point and requires explicit candidate, worktree, immutable source ref, and new evidence-directory environment variables. `make test`, `make check`, and `git diff --check` remain required code-delivery gates. Offline evidence is non-invasive: it does not install or launch the app bundle, change Accessibility permissions, synthesize system input, or touch the physical monitor.
