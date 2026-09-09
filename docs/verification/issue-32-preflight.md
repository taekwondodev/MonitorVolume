# Issue #32: offline preflight, comparison blocked

## Verdict

The current candidates are **not comparable** under the approved topology-only experiment. Neither candidate is cleared for the live campaign by this preflight. Issue #32 remains incomplete: comparative workload execution, timing/resource measurements, and final live-readiness review are blocked, not passed or waived.

Authority: [#28](https://github.com/taekwondodev/ProArtVolume/issues/28), [#32](https://github.com/taekwondodev/ProArtVolume/issues/32), and the joint grilling comment on #32. That comment requires identical policy and instrumentation plus manual full-diff review; it rejects comparison when behavior or common configuration drifts.

## Artifact scope

- Candidate A: `candidate-a/issue-30`, source commit `84f674d`.
- Candidate B: `candidate-b/issue-31`, source commit `ae62d45`.
- Common base: `678e38c`.
- Verification work is isolated on `verification/issue-32`. Both candidate refs and application source remain unchanged.
- `scripts/offline_policy_probe.py` extracts exact committed bytes for the seven Domain dependencies listed in its `SOURCES` closure, compiles them with optimized Swift 6 and complete strict concurrency, and runs one captured copy of `scripts/OfflinePolicyProbe.swift` against each. It retains that probe source and records source, probe, executable, and compiler bindings in local evidence.
- The probe observes Domain transitions only. It does not instantiate a Handler or establish native event reachability. It is not an automated static-diff gate and does not replace manual branch review.

## Executed evidence

| Drive | Observed result | Interpretation |
| --- | --- | --- |
| A/B Domain policy probe | 18 scenarios per candidate, 12 divergent outcomes, exit 1 | Shared policy parity fails |
| Repeated A/B probe | Same 12 divergent outcomes, exit 1 | Deterministic reproduction, not a performance sample |
| A/A control | 18 scenarios per side, zero differences, exit 0 | Probe does not manufacture cross-process divergence |
| B/B control | 18 scenarios per side, zero differences, exit 0 | Same control for B |
| A existing Release harness audit | 8 reported-passing scenarios, 28 events, executable hash verified | Limited common Domain/Service drive, not Handler conformance |
| B existing Release harness audit | 8 reported-passing scenarios, 28 events, executable hash verified | Same limitation |
| A repository gates | 64 Swift tests passed; `make check` and `git diff --check` passed | Necessary baseline checks, not parity or runtime proof |
| B repository gates | 65 Swift tests passed; `make check` and `git diff --check` passed | Different test coverage does not settle the shared policy |

Local raw evidence directories:

- `.hermes/verification/evidence/issue-32-policy-preflight/`
- `.hermes/verification/evidence/issue-32-policy-repeat/`
- `.hermes/verification/evidence/issue-32-policy-aa/`
- `.hermes/verification/evidence/issue-32-policy-bb/`
- `.hermes/verification/evidence/issue-32-harness-audit/`

These contain actual process output. The existing harness reports 6 admitted, 3 completed, 3 discarded, 3 rejected, and 1 overflow in each audited run. These counts describe its controlled Domain/Service scenario sequence only. They are not accepted as counts for the requested repeated/mixed/delayed A/B workload campaign.

## Blocking findings

### P1. Shared sleeping-signal policy differs

`Sources/ProArtVolumeCore/Domain/ControlEligibility.swift:236` differs across the candidates. A ignores only an already suspended phase; B additionally ignores suspension requests during every sleeping phase.

The same actual Domain drive reproduces the difference for each suspension reason after active sleep and after unavailable sleep. The six cases where suspension precedes sleep agree. For example, `active_sleep_signal:permissionRevoked` ends in latched suspension with permission polling disallowed in A, but in validation with permission polling allowed in B after wake.

This establishes non-topology behavior drift. It does **not** establish which policy is correct for a stale owner notification or which native callback interleavings occur. Before copying either implementation, distinguish a current disable/revocation signal from an obsolete owner result and settle the common rule. Both candidates must consume that same rule and scenario matrix.

### P2. Existing offline executable does not exercise either candidate bridge

`Package.swift:33-36` gives `ProArtVolumeOfflineHarness` only the Core dependency. `OfflineContractHarness.swift:577-639` directly routes, dequeues, reduces intent, records an `osd_requested` marker, and submits Service work. Neither `MediaKeyInterceptor` implementation nor `DedicatedMediaKeyTapOwner` is on that path.

Consequently the same passing common harness cannot establish equivalence of callback-to-consumer scheduling, bounded notifications, owner teardown coordination, permission-observation wiring, or pre-presentation stale rejection. Native framework behavior remains a separate runtime obligation, but candidate-bound offline bridge evidence is also absent.

Capacity is another binding gap: harness initialization uses 2 (`OfflineContractHarness.swift:131`); app initialization uses `ControlEligibility()` (`ProArtVolumeApp.swift:32`), whose default is 8 (`ControlEligibility.swift:141`). A and B agree on the app default, but the fixture is not a measurement-driven selection or conformance demonstration of that configured candidate capacity.

### P3. Claimed process-uptime events are logical fixture timestamps

`OfflineContractHarness.swift:673-675` advances a counter by 1,000,000 per call. Its report declares process-uptime timestamps at lines 719-721. Both real audited outputs begin at 0 and end at 42,000,000; all event timestamps are multiples of 1,000,000. The maximum delivery wait is 2,000,000 in both because admission and dequeue use this counter.

Those are logical fixture observations, **not measured delivery latency**. Monotonicity checks in `scripts/offline_comparison.py:420-429` accept the mislabeled clock. Preserve historical values as logical observations; do not reinterpret them as real-time samples. A repaired measurement path must declare and use an actual monotonic clock with explicit phase/event semantics.

### P4. CPU/RAM window names are not backed by their workload

`OfflineContractHarness.swift:678-692` performs array arithmetic until half the requested duration, then sleeps. It does not drive isolated presses, repeated/mixed commands, controlled UI/consumer delays, or lifecycle changes during the resource windows. For the default duration, its busy portion spans nominal active-idle, burst, and part of the nominal suspended window.

`prepareWorkloadState()` chooses one lifecycle state before that loop; window labels do not cause transitions. Real process CPU/RAM sampling of this loop would still be the cost of that loop, not of candidate topology, OSD-facing bursts, or suspension cleanup. Instrumentation events are emitted before this workload, so the full/none subtraction is not a representative instrumentation overhead measurement for the requested workload.

No comparative CPU/RAM figures are published from these windows. Their missing status blocks the campaign; it is not evidence of negligible resource cost.

### P5. Resource summaries cannot be revalidated against retained raw samples

`scripts/offline_comparison.py:522-562` summarizes the in-memory `ps` samples but persists only the aggregate resource report and the Swift stdout/stderr. The raw sample list is lost. `validate_resource_report()` checks structure and some inequalities, not reconstruction from raw samples. Missing polling attempts are omitted rather than counted.

The corrected runner must retain raw samples, failed/censored collection attempts, phase boundaries, and exact sample/run counts, then recompute all summaries from those records. Workload windows must share an observed timing origin with the child. Parent `ps` start time alone is not a workload phase boundary.

### P6. Instrumentation is not a frozen common path

Manual review confirmed that A retains the MainActor-confined diagnostic budget (`InputLifecycleDiagnostics.swift:4-7`), while B uses a shared mutex and calls `logger.notice` inside that lock (`InputLifecycleDiagnostics.swift:83-94`). The need to support multiple threads is a topology consequence, not inherently a correctness defect, but the current implementations do not provide the identical instrumentation required by #32. No measured callback cost is inferred from this difference.

Trace coverage also differs: A surrounds `tapIsEnabled` with diagnostic query records (`MediaKeyInterceptor.swift:111-113`); B's owner status query lacks those records (`DedicatedMediaKeyTapOwner.swift:186-200`). B additionally emits a second `serviceScheduled` marker on successful reopen (`ApplicationCoordinator.swift:142`) after calling the helper which emits it. Align observation semantics before comparison and preserve historical record meanings.

### P7. Pending explicit reopen is handled differently across sleep

Both coordinators set `reopenAfterTapRelease` when an explicit reopen finds a suspended owner still active. A's release delegate retains that intent while sleeping (`ApplicationCoordinator.swift:224-227`), and its suspended-wake branch consumes it (`:197-203`). B's release delegate clears the flag before calling `reopen()` (`ApplicationCoordinator.swift:297-300`), whose sleep guard rejects the call; B's suspended-wake branch does not restore that pending request (`:277-280`).

This is a source-grounded difference in asynchronous teardown handling, not a native reproduction. The required offline lifecycle drive must exercise the sequence: suspend, explicit reopen waiting for release, sleep, release notification, wake. Repair and verify it before declaring Handler parity.

## Coverage and manual review

| Property | Current evidence | Gap |
| --- | --- | --- |
| Intent saturation, mute parity, fresh seed | Existing Domain tests and common harness | Does not exercise candidate consumer wiring |
| Admission and overflow | Shared gate, capacity-2 fixture, common counts | Candidate capacity 8 and held-consumer workload not driven |
| Suspension and wake | Domain probe proves a difference | Common sleeping-signal rule required |
| Active-only permission checks | Domain policy plus source inspection | No executed candidate polling/lifecycle matrix |
| Pairing | Domain tests and recorded fixture events | Candidate bridge coverage and matched assertion matrix required |
| No stale intent/OSD-facing output | Common Service rejection and uninvoked OSD | Actual candidate consumer/presentation boundary not exercised |
| DDC recovery and no replay | Controlled Service tests and harness | Candidate lifecycle wiring plus physical DDC still unproven |
| Callback, delivery, cleanup measurements | Native unavailable; fixture times logical | Actual clocks and candidate-bound offline adapters required |
| CPU/RAM and retention | Existing sampler implementation inspected | Workload-backed windows and retained raw samples required |

Independent read-only review examined both full diffs from the common base and the cross-candidate diff; the lead verified the material findings against source and the Domain probe. It confirmed P1, P2, and the instrumentation difference. Remaining inventory:

- B removes A's pairing-across-eligibility-loss test and adds a sleeping-signal policy test. The pairing implementation remains the same; neither suite alone is the common conformance matrix.
- Suspension-reason mapping moved to a Domain extension in B; the mapping values are equivalent. Textual nonidentity alone is not a parity failure.
- B uses asynchronous AppKit termination with a two-second fallback while A terminates synchronously. Asynchronous cleanup follows the owner topology; the fallback is a candidate-specific liveness behavior requiring explicit treatment, not proof of teardown completion.
- Owner claiming precedes source attachment/enabling in A and follows enabling in B. This ordering difference is verified, but a user-visible input-loss window is not established without reentrancy/scheduling evidence.
- B performs an additional consumer session check. This alone does not prove equivalence or rule out cross-thread invalidation between a check and presentation.
- A's `MainActor.assumeIsolated` is consistent with its stated main-run-loop ownership. No evidence establishes off-owner callbacks, so a speculative crash was not promoted to a finding.

The independent review confirms a failed preflight, not a clean three-axis implementation review. Review of the newly added probe/report is recorded separately in the handoff.

## Required repair sequence

1. Resolve shared sleeping-signal policy and any verified Handler parity/correctness findings. Keep both candidates behaviorally identical except ownership/scheduling. Re-run the same Domain probe and full manual branch review after repair.
2. Establish a candidate-bound offline drive for the actual deferred delivery/lifecycle paths without invoking native tap creation, Accessibility, AppKit presentation, or DDC. Record the boundary and what remains modeled. If this requires changing ownership/contracts, settle that architecture before edits.
3. Align finite capacity, clocks, instrumentation, Release configuration, and the complete conformance matrix. Replace self-asserted success flags with observations at permitted seams.
4. Freeze alternating run order, repeated normal-use versus artificial-stress workloads, raw sampling definitions and phase windows, and repeatability/equivalence criteria before measurements.
5. Execute and validate the repaired gate, including rejected/discarded work and unavailable measurements. Only candidates with resolved correctness failures may advance to separately authorized live work.

## Runtime obligations and safety

Actual tap scheduling, callback duration and timeout behavior; signed-app Accessibility identity and prompts; OSD rendering; native teardown effects on ordinary input; physical DDC control; and native thread/tap/wakeup resource behavior all remain unproven.

No application installation or launch, permission change, synthesized system input, automatic relaunch, or hardware experiment was performed. No raw historical incident capture was edited. The earlier repeated-recreation incident interpretation remains superseded by #28 and ADR 0003; this report does not propose a causal explanation of the freeze.

## Principles that changed execution

- Prove It Works: compiled and exercised the real committed Domain types rather than treating issue closure or common-harness success as parity evidence.
- Build the Lever: added a rerunnable source-bound policy probe with raw output and same-candidate controls.
- Sequence Verifiable Units: stopped performance comparison at the failed correctness/measurement preflight instead of ranking invalid measurements.

## Reproduction

Use a new output directory for each invocation; existing evidence is deliberately not overwritten.

```sh
python3 scripts/offline_policy_probe.py --a candidate-a/issue-30 --b candidate-b/issue-31 --output .hermes/verification/evidence/issue-32-policy-new-run
python3 scripts/offline_policy_probe.py --a candidate-a/issue-30 --b candidate-a/issue-30 --output .hermes/verification/evidence/issue-32-policy-new-aa
python3 scripts/offline_policy_probe.py --a candidate-b/issue-31 --b candidate-b/issue-31 --output .hermes/verification/evidence/issue-32-policy-new-bb
```

Exit 1 means the observed Domain sequences differ. Exit 0 means only the probed sequences agree, not full conformance or live readiness. Compiler/process errors fail the invocation and do not produce a successful parity report.
