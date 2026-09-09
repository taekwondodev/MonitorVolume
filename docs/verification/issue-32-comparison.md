# Issue #32: offline comparison result

## Verdict

The repaired Candidate A and Candidate B comparison is **inconclusive**. No candidate is selected, and neither candidate is cleared for live testing by this offline experiment.

The complete frozen campaign produced valid, reconstructable evidence, but it did not produce a comparable winner:

- required performance classifications favor both candidates;
- four required performance comparisons are indeterminate;
- the candidates produce deterministic accounting differences under the shared workload;
- the frozen protocol did not explicitly classify cross-candidate accounting differences, although the pinned collector conservatively treated them as disqualifying.

Changing that analysis rule after seeing the results would introduce post-observation bias. Campaign v2 therefore remains the final result of this offline phase and is preserved as inconclusive.

Authority: issues #28 and #32, ADR 0003, and `scripts/issue32_collection_protocol.json`.

## Candidate and artifact scope

- Historical Candidate A ref: `84f674d36fec021cf25ebbbc561dc60d312b1923`.
- Historical Candidate B ref: `ae62d45586793495a052e25403b9cd748ac8715d`.
- The original refs remain unchanged.
- Repaired Candidate A ref: `e0817591aab903b061c3d7267f03a6e6c3cb9fb5`.
- Repaired Candidate B ref: `00fd9e52517e31890899c62e3a2fb6671dfc36c3`.
- Each repaired candidate was built from its isolated repair worktree. Every run retains the exact source closure and executable hash.
- The committed Candidate A source closure matches all 36 SHA-256 file bindings retained by campaign v2; the committed Candidate B source closure matches all 37. The commits therefore bind the exact measured source bytes without rerunning or mutating the campaign.

Campaign v2's retained `sourceRef` and `resolvedSourceRef` fields name the historical input refs, while each retained `sourceClosure` names the bytes actually compiled from the then-dirty repair worktree. The historical commits contain only 22 of the 36 and 37 measured file versions, respectively, so those ref fields must not be read as commit-to-bytes identity. The new repaired refs close that delivery gap by containing every measured source-closure byte.

The experiment uses disposable candidate-bound conformance executables. It does not install or launch the app bundle.

## Campaign history

### Preserved failed campaign v1

`.hermes/verification/evidence/issue-32-comparative-campaign-v1/` stopped during warmup on Candidate A's stress workload. The report contained:

- admission attempts: 16;
- admitted: 8;
- rejected: 16.

The failure exposed a real accounting defect. `InputAdmissionMetrics.attemptedCount` counted key-down admission attempts, while `rejectedCount` also counted unmatched key-up pass-through. Both repaired candidates now leave admission counters unchanged for unmatched key-up. A regression assertion failed before the one-line repair and passed afterward.

Post-repair verification completed before another comparative observation:

- 67 Swift tests passed in each repair worktree;
- `make check` and `git diff --check` passed in each repair worktree;
- 40 focused tooling tests passed in the verification checkout;
- 12 fresh v14 gates covered both candidates, both workloads, and both instrumentation modes;
- eight v14 repeatability and instrumentation controls returned no failures;
- the six-report v14 control manifest validated;
- independent Standards, Spec, and Adversarial review returned GREEN.

The failed v1 directory remains preserved and was not reused.

### Complete campaign v2

Authoritative evidence: `.hermes/verification/evidence/issue-32-comparative-campaign-v2/`.

| Property | Result |
| --- | --- |
| Warmup runs | 8 retained |
| Measured runs | 160 selected |
| Replacements | 0 |
| Selected key matrix | Exact 20 rounds by 2 workloads by 2 candidates by 2 instrumentation modes |
| Environment observations | 84, all invariant |
| Power and thermal requirements | AC power, low-power mode off, nominal thermal state |
| Failed resource polls | 0 |
| Gate or child failures | 0 |
| Report digest mismatches | 0 |
| Raw reconstruction failures | 0 |
| Selected reports failing full revalidation | 0 of 160 |
| Final status | `inconclusive` |
| Provisional candidate selection | `inconclusive` |

Each measured run retains one trailing `processExitedBeforeNextPoll` censor after process exit. The protocol retains and excludes that observation from numeric summaries. It does not remove a required sample or invalidate a paired round.

Artifact digests after explicit reanalysis:

- campaign state: `fbf4947e89bb0f51da52ebb3bee01d6acc53a4f4711df4f9b2622135f171d8c1`;
- analysis: `dc7d59845038f190e09044895451c9760ae44a7e691251cdd42c222321220845`;
- v14 control manifest: `ad535015f962d23992b4a122fcb1515b24634dd96b808304e8f831d6c33e904d`.

## Comparative observations

The analysis contains 274 predeclared timing, CPU, and memory comparisons:

| Classification | Count |
| --- | ---: |
| Candidate A better | 120 |
| Candidate B better | 18 |
| Equivalent | 132 |
| Inconclusive | 4 |

These counts are individual phase, statistic, workload, and instrumentation comparisons. They are not independent votes and must not be collapsed into a majority score.

The mixed direction alone prevents selection under the frozen rules. Timing comparisons in both normal and stress full-instrumentation workloads include nine results favoring A and nine favoring B. Memory comparisons favor A, while CPU comparisons are mostly equivalent and four normal, inactive-instrumentation comparisons are inconclusive.

### Deterministic workload accounting difference

All 20 stress rounds, in both full and inactive instrumentation modes, report the same repeated-burst difference:

| Repeated-burst field | Candidate A | Candidate B |
| --- | ---: | ---: |
| Input events | 32 | 32 |
| Admission attempts | 16 | 16 |
| Admitted | 8 | 16 |
| Rejected | 8 | 0 |
| Discarded | 8 | 0 |
| Overflow | 1 | 0 |
| Delivered commands | 0 | 16 |
| Passed-through events | 16 | 0 |
| Peak outstanding | 8 | 1 |

Candidate A accumulates to capacity, overflows, latches suspension, and discards its queued deliveries. Candidate B drains between requests and completes all 16 commands. Normal repeated and mixed bursts also produce different peak occupancy.

Candidate B therefore never reaches the configured capacity in this comparative stress phase: its real scheduling path drains at a peak outstanding count of one. This table is not equal-saturation evidence for Candidate B. The separate deterministic conformance matrix proves the configured-capacity contract; the comparative table records how each topology behaved under the shared stress workload.

The shared typed input sequence is identical, and every candidate report reconciles its own accounting identities. The difference is therefore a repeatable candidate-topology observation, not missing data or corrupt evidence.

## Interpretation constraint

`scripts/issue32_collector.py` was reviewed and hash-pinned before collection. Its analysis treats any cross-candidate accounting difference as an exact-accounting failure and forces an inconclusive status.

Final Adversarial review found that this cross-candidate equality rule is not explicit in the frozen protocol. The protocol clearly requires every run to retain and reconstruct exact accounting fields, and it requires correctness before performance selection, but it does not define whether unequal valid counts are a correctness failure or a candidate-ranking signal.

The finding does not permit a different v2 result:

1. Removing the rule after observation would change the methodology after seeing candidate behavior.
2. The frozen performance classifications independently favor both candidates and include indeterminate metrics.
3. No predeclared rule converts rejected, discarded, overflow, or delivery counts into a winner.

The approved decision is to close this offline phase with the explicit inconclusive outcome. A future experiment may define a new accounting classification before collecting fresh observations, but it cannot reinterpret v2 in place.

## Proof boundary

The campaign measures the disposable conformance process at the typed post-parse bridge and candidate-owned consumer seams. It measures process CPU and resident memory for that executable. It models only the OSD-facing handoff.

The campaign does not prove:

- native CoreGraphics callback scheduling, tap timeout, creation, or teardown behavior;
- Accessibility identity, permission prompts, or regrant behavior;
- AppKit OSD rendering or display scanout;
- effects on ordinary system input or input-path restoration;
- physical DDC behavior or monitor state;
- native wakeup counters;
- installed application CPU, memory, lifecycle, or cold-launch behavior.

No app installation or launch, permission change, CoreGraphics event construction or posting, synthetic input, sleep or wake operation, DDC command, or physical hardware operation was performed.

## Review status and open delivery work

- Pre-campaign accounting-repair review: Standards GREEN, Spec GREEN, Adversarial GREEN.
- Final campaign evidence review: Standards GREEN; Spec substantially passes with the uncommitted repair-ref gap; Adversarial blocks any claim that cross-candidate accounting equality was explicitly predeclared.
- The Adversarial finding is resolved for delivery by preserving v2 as inconclusive and declining any post-observation reinterpretation. It is not resolved by selecting either candidate.
- Distinct committed repair refs now bind the exact measured Candidate A and Candidate B source closures. Publication and issue closure deliver this report without changing the observed campaign or its interpretation.
- Live testing remains blocked because issue #32 produced no selected candidate and no live-readiness verdict.

## Reproduction and audit

The exact campaign can be audited without collecting again:

```sh
python3 scripts/issue32_collector.py analyze \
  --campaign-dir .hermes/verification/evidence/issue-32-comparative-campaign-v2
```

Exit 1 with `status: inconclusive` is the expected result. Analysis revalidates the protocol, collector, apparatus, expected matrix, complete 160-key selection, report digests, source and configuration bindings, child status, scenarios, topology, raw reconstruction, and behavior fingerprints before deriving metrics.

Campaign v1, campaign v2, v14 gates, v14 controls, and all earlier evidence directories are immutable historical evidence and must remain preserved.
