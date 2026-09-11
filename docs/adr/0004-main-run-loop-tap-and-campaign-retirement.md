# ADR 0004: Keep the media-key tap on the main run loop and retire the comparison campaign

- Status: Accepted
- Date: 2026-09-11
- Tracking issues: [#28](https://github.com/taekwondodev/ProArtVolume/issues/28), [#32](https://github.com/taekwondodev/ProArtVolume/issues/32), [#33](https://github.com/taekwondodev/ProArtVolume/issues/33)
- Supersedes the offline conformance drive and comparative apparatus described in ADR 0003; the lifecycle rules in ADR 0003 remain in force.

## Context

Issue #28 asked whether the media-key event tap should stay on the main run loop (Candidate A) or move to a dedicated thread and run loop in the same process (Candidate B), under the shared suspension contract of ADR 0003. Both candidates were implemented and installed as separate application identities, and a measurement campaign with signed bundles, protocols, evidence directories, and a Python runner was built around them.

The user tried both installed candidates by hand on 2026-09-11 with the same procedure: launch, use the volume keys, then remove the Accessibility grant while the app runs. Both candidates behaved identically:

1. after the grant was removed, the app kept receiving events and showing its OSD for a short time;
2. then mouse and keyboard input froze system-wide for a few seconds;
3. input came back on its own, and from that point the app received no further input.

Because the failure is identical on both topologies, callback scheduling is not the cause, and the comparison had nothing left to decide. The campaign had grown to roughly three times the size of the application it was measuring and had not produced a verdict after several days.

## Decision

- The tap stays on the main run loop (Candidate A). At observed parity the simpler topology wins, as #28 already stated.
- Candidate B (`DedicatedMediaKeyTapOwner`) is not merged. Its branch is deleted.
- The comparison campaign is removed entirely: offline harness, Issue 32/33 collectors and protocols, latency recorder and measured repositories, `verify-proart-volume` project skill, verification documents, and the evidence store. The command surface returns to `test`, `check`, `build`, `verify`, `clean`.
- Future verification of this utility is the existing test suite, `make build`, and the user exercising the feature on the real monitor. A larger apparatus requires an explicit decision by the user.

## Open defect carried forward

Removing the Accessibility grant while the app runs still produces the sequence above. This is the incident that opened #28 and it is not fixed by the suspension contract alone. Facts established so far:

- The captured trace from the earlier incident shows no repeated tap recreation; the tap that exists after regrant receives timeout signals and stays enabled. Recreation is not the mechanism.
- The OSD continuing after revocation shows the tap is still registered and still delivering events to the process for a while after trust is withdrawn.
- The freeze and self-recovery match the system disabling a tap whose owner stopped servicing it in time, with queued system input released afterwards.

Working hypothesis for the fix: detect the loss of trust before the system acts on it (tighter `AXIsProcessTrusted` observation than the one-second poll, or an earlier signal), and on detection invalidate and release the tap synchronously and immediately rather than entering a suspended state that leaves the tap registered. In every state, including suspended, the callback must return the event untouched within microseconds.

The fix is sized as a small change: reproduce with the installed app, write the expected line and confirm it with the user, add one regression test at the `ControlEligibility` or interceptor seam, change the code, `make test`, `make build`, and the user repeats the manual revocation once.

## Consequences

- The application loses its optional latency instrumentation. Latency is judged by use, not by trace.
- `InputLifecycleDiagnostics` (opt-in unified-log records behind a launch flag) is kept as the only diagnostic path because it costs nothing when disabled and is the tool for the open defect above.
- ADR 0003's description of the offline conformance runner and apparatus phases is historical; the lifecycle rules in its Decision section remain the contract the code implements.
