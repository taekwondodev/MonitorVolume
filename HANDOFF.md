# Handoff: issue #33 two-identity live comparison

## Task

Implement the revised two-identity specification in GitHub issue #33 and resume its installed comparison through explicit runtime consent boundaries. `to-tickets` was intentionally skipped. The approved v7 correction changes only the shared lifecycle record limit from 2,048 to 65,536, retains direct terminal operation, and verifies one ordinal at a time.

## Current state

The offline runner implementation and v5 two-identity setup are complete. Campaign v5 is an immutable, inconclusive runtime fixed point. Campaign v6 is a superseded preparation of the old 2,048-record contract with zero measured runs and no valid setup receipt. Candidate A and B now use a 65,536-record lifecycle budget at new clean local refs. Campaign v7 is prepared and both exact retained v7 bundles are installed. A setup attempt was deliberately aborted at Candidate A's manual-grant prompt when the user requested a session handoff. V7 still has zero runs and no setup receipt. All runtime consent expires at this session boundary.

- Primary repository: `/Users/taekwondodev/Developer/ProArtVolume`
- Primary branch: `verification/issue-33`
- Candidate A worktree: `/private/tmp/ProArtVolume-issue-32-a`
- Candidate B worktree: `/private/tmp/ProArtVolume-issue-32-b`
- Candidate A pinned ref: `a3c45b757261488b7857374a3fa1ac88d18994ba`
- Candidate B pinned ref: `ea5a3231e52c8fd908819e0caec3735b6711de2b`
- Current prepared campaign: `.hermes/verification/evidence/issue-33-live-campaign-v7`
- Superseded prepared campaign: `.hermes/verification/evidence/issue-33-live-campaign-v6`
- Campaign v6 has schema 2, two signed old-budget candidate bundles, zero measured runs, and no valid setup receipt.
- Campaign v7 has schema 2, signed Candidate A/B bundles, 16 unchanged normal runs, four separately authorized acceptance runs, zero collected runs, and no setup receipt.
- Both installed v7 executables match the v7 manifest: A `9786bd07d4d1667f239be89490e5418ca0455723706c8063f26686d7309fbd44`, B `c5295724c8d5686dabfec83e7d684ae6f77c8d1bf9d56b1e2ceaa3dd67b28361`.
- Campaign v5 remains at `.hermes/verification/evidence/issue-33-live-campaign-v5` as historical failed evidence.
- Campaign v5 has schema 2, a passed setup receipt, and two preserved failed normal runs.
- Normal ordinal 1, Candidate A/full, failed because the fixed 2,048-record lifecycle budget exhausted after chat-mediated delays, leaving `permissionPoll` unfinished.
- Normal ordinal 2, Candidate B/full, was stopped before physical input after the systematic apparatus mechanism was identified.
- The installed Candidate A and Candidate B bundles predate the 65,536-record commits and are not valid v7 artifacts.
- Exact post-failure process checks returned zero for Candidate A, Candidate B, and production.
- Campaign v7 must use a new evidence directory and the new refs while preserving the v6 runner, schedule, identities, polling cadence, telemetry schema, and all behavior except the shared budget limit. The protocol changes only its two candidate source-ref bindings.
- Campaign v4 is retained unchanged but superseded by v5 after review-driven fixes.
- Campaigns v2 and v3 remain unchanged historical evidence.

## Settled design

1. Production, Candidate A, and Candidate B are explicit application identities.
2. Candidate bundle identifiers, names, installed bundle paths, and installed executable paths are deterministic and pairwise distinct.
3. Candidate preparation rewrites only the declared identity metadata, signs each bundle, and retains executable, metadata, bundle-closure, designated-requirement, source-closure, protocol, and runner bindings.
4. Setup installs both candidate identities and obtains manual Accessibility confirmation once per identity. It neither installs over nor signals the production application.
5. Every setup/run launch requires a candidate-bound one-shot readiness record containing candidate, bundle identifier, actual executable SHA-256, source ref, process-attributed log identity, lifecycle generation, Accessibility trust, tap ownership, and successful current-generation Service validation.
6. A selected run starts only after both other known identities are stopped, revalidates the installed bundle immediately before launch, requires one exact process owner, and stops the launched candidate on every exit path.
7. Emergency stop and cleanup validate retained protocol/manifest application identity and installed executable identity, but intentionally do not require the current runner to match the prepared runner. This keeps recovery available after a runner repair.
8. Cleanup removes only candidate bundles, never signals or removes production, verifies all known identities are stopped, and verifies the production bundle closure is unchanged when present.
9. Publishable projections remove paths, PIDs, process start identity, host/toolchain identity, raw commands, logical CPU count, and machine-specific Accessibility details.
10. Final analysis separates verified facts, manual observations, unavailable/unexercised scenarios, and residual risks. A naturally absent `disabledTap` observation is reported unavailable rather than forced.
11. Metric classification is bound to the protocol's lower-is-better metric set.
12. Campaign v5 remains immutable. Its failed ordinals are not completed, replaced, reclassified, or added to v6.
13. Campaign v7 changes the identical lifecycle budget in both candidates from 2,048 to 65,536 and changes no other candidate behavior.
14. The operator types `START`, `DONE`, and `USABLE` directly in the active runner Terminal.
15. V7 executes one ordinal at a time. The next ordinal starts only after report/digest validation and exact zero-process verification.
16. V7 installs its changed retained bundles, records a new setup receipt, and requires fresh readiness for both candidates.
17. An isolated failed run may advance only after preserved evidence, safe input, and zero-process cleanup. Input disruption or systematic apparatus failure stops collection.

## Candidate instrumentation

Both candidates contain the same readiness model and reporter:

- `Sources/ProArtVolume/Domain/CampaignReadiness.swift`
- `Sources/ProArtVolume/Handler/CampaignReadinessReporter.swift`
- startup integration in `ProArtVolumeApp.swift` and `ApplicationCoordinator.swift`
- tests in `Tests/ProArtVolumeTests/InputLifecycleDiagnosticTests.swift`

Malformed readiness arguments fail closed without aborting ordinary app startup. Candidate A retains main-actor tap ownership; Candidate B retains dedicated-owner-thread tap ownership.

## Verification completed

- Primary `make test`: passed, including 45 focused issue #33 tooling regressions.
- Primary `make check`: passed with strict-concurrency Release build and tooling checks.
- Candidate A `make test` at the 65,536-record ref: 71 tests passed.
- Candidate A `make check` at the 65,536-record ref: passed.
- Candidate B `make test` at the 65,536-record ref: 71 tests passed.
- Candidate B `make check` at the 65,536-record ref: passed.
- `make issue33-doctor` with both 65,536-record worktrees: `readyForOfflinePreparation` and protocol SHA-256 `877fe9b637031e6918d8a8bf50582c1a9ae2ba8433178ae95d7d4d921244bed2`.
- Candidate worktrees are clean at the pinned refs.
- Campaign v5 preparation succeeded without install or launch.
- Offline campaign validation confirmed both prepared bundles' code signatures, designated requirements, executable/Info.plist/notices digests, complete bundle closures, and source closures.
- Campaign v5 setup passed with a manifest-bound receipt and fresh readiness for both candidate identities.
- Candidate A/B installed bundles are present, signed, and executable-hash-bound to the campaign manifest.
- Candidate A and Candidate B both attested Accessibility trust, active tap ownership, and successful current-generation Service validation.
- Campaign v5 normal ordinal 1 preserved a failed report after lifecycle record 2,049 emitted `budgetExhausted`; the operator observed correct app behavior and usable input.
- Campaign v5 normal ordinal 2 preserved a pre-input failure after the systematic operator-channel problem was identified.
- Exact post-failure process checks returned zero for Candidate A, Candidate B, and production.
- Campaign v6 preparation succeeded without install or launch.
- V6 retained candidate code signatures are valid, both worktrees are clean at the pinned refs, and the manifest contains zero runs and no setup.
- V6-to-v5 comparison passed for runner, protocol, schedule, source refs, executable digests, bundle closures, and application identities.
- Candidate A commit `a3c45b7` and Candidate B commit `ea5a323` change only the shared lifecycle budget and the matching literals in the existing Domain test.
- The v7 protocol changes only the two candidate source-ref bindings; `make issue33-protocol`, primary `make test`, and primary `make check` pass.
- The revised GitHub issue body is byte-identical to `.hermes/tmp/issue-33-v7-spec.md` and remains open with `bug` plus `ready-for-agent`.
- Campaign v7 offline preparation passed. Its protocol SHA-256 is `877fe9b637031e6918d8a8bf50582c1a9ae2ba8433178ae95d7d4d921244bed2`; runner SHA-256 is `a788d9c47b2427e562e251a53407bb6cbfad3f1e8abcebeb9673b3db66bfea98`; both retained bundle signatures validate; both source worktrees remain clean.
- Post-preparation checks show zero Candidate A, Candidate B, and production processes.
- Campaign v6 cleanup passed after the user manually removed both Accessibility entries. It removed only A and B and reported production unchanged.
- The first v7 setup attempt failed before launch because the old v6 bundles were still installed. After v6 cleanup, the second setup installed both exact v7 bundles and reached Candidate A's grant prompt. It was deliberately answered `ABORT` for this handoff, failed without a setup receipt, and `make issue33-stop` confirmed zero candidate processes.
- `git diff --check`: passed.

## Independent review

Initial DeepSeek V4.1 Flash reviews ran independently on Standards, Spec, and Adversarial axes.

Blocking findings were fixed:

- publishable output retained host/machine identity;
- final analysis omitted verified/manual/unavailable/residual-risk sections;
- emergency stop depended on current runner provenance.

Low-cost hardening also removed dead production globals, removed an unused production installer, avoided campaign-argument `fatalError`, bound metric directionality, guarded empty instrumentation rounds, fixed a self-graded metric fixture, and refreshed this handoff.

Final independent Standards, Spec, and Adversarial re-reviews all passed with no blocker. The offline fixed point is complete.

The 65,536-record delta received a fresh independent DeepSeek V4.1 Flash review on all three axes. Standards found no hard violation, Spec found full conformance with no scope creep, and Adversarial found no `act on`. Its two `consider` notes are the bounded 32× worst-case unified-log volume and the fact that sufficiency still requires native runtime proof; neither changes the approved scope or gates.

## Runtime boundary

Do not perform campaign v7 setup or collect a run without new explicit user authorization in the new session.

The next state-changing operation is a fresh setup for campaign v7. The exact v7 bundles are already installed, so setup should validate them, launch A and B sequentially, receive manual Accessibility confirmations through chat, and submit `GRANTED` to the hidden setup PTY only after each user confirmation. Do not focus or expose the runner terminal. A passed setup receipt, fresh readiness for both candidates, and exact zero-process verification complete this unit.

Normal runs require another explicit consent for physical media-key input, resulting DDC writes, and normal UI activity. Lifecycle/sleep-wake and stress each require separate explicit authorization. No prior consent carries forward.

The latest user decision is to drive setup and measured acknowledgements through chat because the lifecycle budget is now 65,536 records. GitHub issue #33 and the live-comparison skill still describe direct terminal acknowledgements for measured runs. Reconcile those durable contracts with the latest explicit decision before collection. Do not reduce the budget, change the runner, schedule, polling cadence, telemetry schema, workload, or evidence gates.

Do not run `make build`; it targets the production application identity and is not part of campaign setup.

## What did not work

- V6 used two visible terminals, and the user entered `GRANTED` in the wrong one. Use one hidden setup PTY and chat confirmations.
- V7 setup cannot overwrite old signed candidates. V6 cleanup has now removed them, and the exact v7 bundles are installed.
- The interrupted v7 setup is not reusable. It produced no receipt and no run. Start setup again after fresh consent.

## Pending

1. Reconcile this handoff with live repository, campaign, installed-bundle, and process state.
2. Align issue #33 and the project verification instructions with chat-mediated acknowledgements, preserving every other v7 contract.
3. Obtain fresh setup consent, complete setup through chat, validate its receipt and readiness, and prove zero processes.
4. Obtain separate normal-run consent, then collect the 16 scheduled normal runs one at a time. Verify each report digest and zero-process state before advancing.
5. Obtain separate authorization before lifecycle/sleep-wake or stress work.
6. Analyze and publish only after complete evidence, then run fixed-point Standards, Spec, and Adversarial review.

## Next completion criterion

Campaign v7 has one passed setup receipt with fresh readiness for Candidate A and Candidate B, both installed executables still match the manifest, and Candidate A, Candidate B, and production have exactly zero processes. No physical media-key or DDC activity occurs during this unit.

## Active skills

- `session-pickup`
- `dev-cycle`
- `implement`
- `pause-safely`

## Resume Prompt

`/session-pickup`

`/implement #33`

Read `HANDOFF.md` and treat it as the session bridge for ProArtVolume issue #33. Reconcile it with the live repository, campaign v7, installed bundles, and process state. Continue from Pending. The latest operator-channel decision is chat-mediated acknowledgement with the 65,536-record lifecycle budget; align durable contracts before collection. Infer no consent from this handoff or the prior session. Ask me nothing until you have read and reconciled the handoff.
