# Issue #33: installed A/B preflight and run contract

## Status

Campaign v5 is an immutable, inconclusive runtime fixed point. Its two-identity setup passed with fresh readiness for Candidate A and Candidate B. Normal ordinal 1 then failed evidence validation after chat-mediated operator delays exhausted the fixed 2,048-record lifecycle budget, leaving a `permissionPoll` operation unfinished. The operator observed the application OSD and DDC effects and confirmed ordinary input usability, so this is an apparatus failure rather than candidate-performance evidence. Normal ordinal 2 was stopped before physical input after the systematic mechanism was identified. Both reports remain bound in the v5 manifest, and exact process checks returned zero for Candidate A, Candidate B, and production.

Campaign v6 is a superseded preparation of the 2,048-record contract with zero measured runs and no valid setup receipt. Campaign v7 is **not prepared and is not authorized for setup or collection**. Candidate A and B now share a 65,536-record lifecycle budget; runner, 16-run schedule, permission-poll cadence, telemetry schema, exhaustion behavior, and all other candidate behavior remain unchanged. The protocol changes only its two candidate source-ref bindings. Normal collection requires new consent for physical media-key input, resulting DDC writes, and normal UI activity. Stress and lifecycle/sleep-wake remain separate future authorizations. No consent is inferred from the issue label, earlier setup, prior collection consent, or source changes.

Issue #32 remains historically inconclusive. Its candidate-bound correctness, integrity, repeatability, and instrumentation gates are accepted as readiness evidence for this ticket; its campaign, collector result, and report are not reinterpreted. The installed campaign compares both repaired candidates under a new rule frozen before any installed observation.

## Candidate and source shape

- Candidate A starts from repaired ref `e0817591aab903b061c3d7267f03a6e6c3cb9fb5` and retains main-run-loop tap ownership.
- Candidate B starts from repaired ref `00fd9e52517e31890899c62e3a2fb6671dfc36c3` and retains dedicated-thread/run-loop tap ownership.
- Candidate A ref `a3c45b757261488b7857374a3fa1ac88d18994ba` and Candidate B ref `ea5a3231e52c8fd908819e0caec3735b6711de2b` retain equivalent schema-3 instrumentation and the same opt-in one-shot readiness contract, with the identical bounded lifecycle limit raised from 2,048 to 65,536. Each attests its actual executable hash, candidate/bundle/source identity, process-attributed lifecycle generation, Accessibility trust, tap ownership, and successful current-generation Service validation; malformed campaign arguments fail closed without aborting ordinary app startup.
- The event timestamp and callback recorder use startup-relative nanosecond clocks. Their difference is reported as a delivery proxy that includes upstream delay, not pure run-loop wait. The final snapshot binds capacity, occupancy, completion, rejection, discard, overflow, and pending work after teardown.

## Architecture

The candidate application code remains the measured behavior. Campaign-only metadata gives A and B distinct bundle identifiers, display names, signed bundles, and installed paths while leaving the production manifest and build path unchanged. No benchmark-only Service lifecycle or second hardware owner is introduced.

1. The candidate Handler records bounded schema-3 lifecycle events through the existing opt-in unified-log channel. Callback entry carries the source event timestamp; callback exit, handoff, tap, permission, suspension, revalidation, and teardown records retain their existing meanings.
2. The existing schema-2 latency recorder remains the source for accepted-input, intent, OSD draw, Service, and DDC timing. It is enabled only in full instrumentation mode.
3. `scripts/issue33_live.py` owns preparation, setup, collection, analysis, stop, and cleanup through one validated identity descriptor per candidate. Preparation validates clean pinned worktrees, builds each Release executable once, assembles and signs the final distinct bundles, retains source closures plus artifact/metadata/designated-requirement bindings, and compiles the environment probe without installing or launching either app.
4. A separately consented setup installs both byte-identical retained bundles, launches them sequentially through LaunchServices for manual grants, and requires fresh per-candidate readiness without physical input or TCC automation. Measured runs never reinstall or re-sign: they revalidate both installed identities, prove production/A/B stopped, launch only the scheduled candidate, require fresh readiness, and only then sample that PID and show physical operator phases.
5. Parent-monotonic operator boundaries attribute resource samples to phases. Full instrumentation additionally uses app uptime records and a final eligibility-accounting snapshot with the frozen capacity, attempted, admitted, rejected, discarded, overflow, completed, peak-outstanding, and pending counts. Every CPU, RAM, wakeup, thread-count, failed, censored, and process-start-identity sample, environment observation, executable, source closure, protocol, runner, and raw trace is retained.
6. Normal run cleanup requests a normal application quit. Failure and emergency cleanup inspect both candidate identities, validate a running bundle before signalling, never signal production, and converge known processes to zero. Final campaign cleanup removes only the two manifest-bound candidate bundles after manual Accessibility-entry removal is recorded and verifies the production bundle unchanged.

## Frozen workload

The protocol contains four counterbalanced normal rounds for each candidate in full and inactive instrumentation modes: 16 normal runs. Balanced physical key sequences cover active idle, isolated up/down and mute pairs, repeated and mixed bursts, realistic pointer/window activity during an OSD burst, and post-burst retention. The balanced sequence must return volume and mute intent to the starting state.

Two full-instrumentation lifecycle runs cover permission revoke, pass-through while suspended, regrant without recovery, explicit reopen with fresh validation, and separately authorized sleep/wake. A naturally occurring disabled-tap event is retained; the run does not synthesize input or induce an unsafe stall to manufacture one. Two separate full-instrumentation stress runs cover rapid balanced bursts and ordinary-input usability.

## V7 operator channel

V7 executes one ordinal at a time. After the runner passes readiness, the operator interacts directly with that runner Terminal. The operator reads each frozen phase instruction, types `START`, performs the action, waits at least the minimum, types `DONE`, and types `USABLE` only after confirming ordinary keyboard and pointer usability. Chat and other mediated acknowledgements remain outside the active instrumented run.

After each runner exits, the driving agent validates the report and manifest digest and verifies zero Candidate A, Candidate B, and production processes before launching the next ordinal. An isolated failed run may be followed by the next scheduled ordinal only when its evidence is preserved, cleanup converges to zero, and input remains safe. Input disruption or a systematic apparatus failure stops collection.

## Accounting decision

The issue #32 ambiguity is removed before observation:

- every candidate run must reconcile its own admission, delivery, pass-through, rejection, discard, overflow, and completion identities;
- cross-candidate exact count equality is not required because topology can change scheduling and occupancy;
- any rejection, discard, or overflow in the normal workload is a correctness failure;
- under separately labelled stress, fewer losses and more completed commands are candidate evidence only when ordinary input remains usable;
- faster timing from a surviving subset cannot compensate for lost work.

## Selection rule

Required correctness, availability, evidence-integrity, and input-safety gates precede performance. Paired normal-run summaries use the frozen bootstrap seed and the same-candidate successive-run noise band. At measurable parity Candidate A is preferred. Candidate B requires at least one required metric favoring B, no required metric favoring A, and a clean lifecycle-ownership review. Missing evidence, a failed gate, an indeterminate metric, or mixed winners yields an explicit inconclusive result. Stress remains a gate and secondary evidence, not normal performance.

The comparison does not prove the historical freeze resolved, authorize production integration, or close issues #28 or #26.

## Alternatives rejected

- A second in-app JSON lifecycle recorder would add callback allocations, persistence behavior, and shared synchronization to both candidates. The existing bounded unified-log channel already records the required lifecycle path and fails visibly on loss, so only the missing source-event timestamp is added.
- A media-key emergency chord would consume or reinterpret user input inside the product and could fail on the same path under investigation. The prepared Terminal command is outside the event tap and targets the exact installed executable.
- Reusing the issue #32 collector would relabel typed post-parse conformance events as native framework evidence. The live runner instead reuses only its proven binding, environment, raw-sampling, and fail-closed patterns.
- Requiring cross-candidate equality for stress accounting would repeat issue #32's undeclared rule. The new protocol treats internally valid topology-dependent occupancy as evidence while making any normal-workload loss a correctness failure.

## Threat model and mitigations

Protected assets are ordinary keyboard and pointer availability, Accessibility choices, the production application, physical monitor state, single tap/DDC ownership, candidate attribution, and evidence privacy. The operator can grant/revoke permission and provide physical input; macOS owns event delivery and permission UI; the collector owns only the two manifest-bound campaign applications and their local evidence.

- Denial of input service is mitigated by serial runs, a prepared exact-process keyboard stop, immediate abort on disruption, no watchdog, and no automatic relaunch.
- Duplicate ownership and hardware races are mitigated by the app's tap-owner claim, zero production/other-candidate processes, exactly one selected executable-path process, and one campaign lock held across setup or a run.
- Evidence substitution is mitigated by distinct bundle identities, clean pinned refs, full source closures, retained signed bundles, executable/metadata/bundle-closure SHA-256 checks, designated requirements, and protocol/runner digests revalidated before setup, collection, stop, cleanup, and analysis.
- Privacy exposure is mitigated by fixed-field lifecycle records without key codes, pointer data, volume values, machine paths, or user identifiers in the publishable projection.
- Permission tampering is mitigated by two explicit candidate identities and manual permission changes only. The app may request the native prompt on setup launch or explicit reopen; tooling never grants, revokes, reads, or edits TCC state directly.

Residual risks are a native event-tap or WindowServer failure whose mechanism is still unknown, unified-log loss that forces an incomplete result, an already-started DDC call that cannot be retroactively cancelled, and unavailable disabled-tap evidence when no safe natural occurrence is observed.

## Principles that changed choices

- **Foundational Thinking:** source, executable, process, protocol, run, consent, and evidence identities are explicit manifest data before collection rather than inferred from the current checkout.
- **Build the Lever:** one rerunnable protocol validator and collector replace manual candidate switching, resource sampling, attribution, and report scrubbing.
- **Sequence Verifiable Units:** protocol validation, schema-3 diagnostics, offline preparation, normal runs, lifecycle runs, stress runs, analysis, and publication are separate gates; no later gate can turn an earlier failure into a pass.
- **Fix Root Causes:** v7 increases only the bounded telemetry capacity and keeps the direct terminal channel rather than weakening evidence completeness.
- **Prove It Works:** selection requires the signed installed bundle, physical input, exact process evidence, retained framework traces, and cleanup; builds and offline conformance remain prerequisites, not runtime proof.
- **Never Block on the Human:** offline protocol, tooling, tests, and build preparation proceed without interruption; execution stops only at the explicit consent and physical-observation boundary owned by the user.

## Verification boundary

Protocol validation, parser/accounting tests, strict-concurrency builds, and candidate tests are non-invasive. They do not establish native input availability. A real claim requires the signed installed Release app, its exact process and executable hash, physical input, retained traces, operator observations, and exact cleanup. Visual OSD quality remains manual.
