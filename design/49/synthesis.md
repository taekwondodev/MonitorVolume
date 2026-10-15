# Synthesis for issue #49: companion and remote ingress architecture

Candidates: `design/49/synthetic/` (this branch, `design/49-synthetic`, commit `1ad6737`) and `design/49/direct/` (branch `design/49-direct`, commit `e9a8dd9`). Both were produced independently from the same grounding and screened against the same settled decisions of map #41.

## Synthesis decision

**Base: the synthetic key ingress candidate.** Its rationale, module map, type sketch, and project layout in `design/49/synthetic/` are the contract, amended by the grafts and corrections below.

Why it won:
- **Contract fidelity.** Decision #47 requires every remote command to follow the physical-key rule: consumed for the target monitor when eligible, otherwise left to macOS (system volume and native OSD). Posting the same system-defined event a physical key produces satisfies this by construction. The direct candidate explicitly leaves unroutable remote commands unhandled (`design/49/direct/rationale.md`, Tradeoffs), which contradicts #47; honoring #47 there would need either a CoreAudio system-volume path that duplicates macOS behavior without its OSD, or posting synthetic events anyway.
- **Interface depth and subtraction.** `MonitorVolumeCore`, the event tap, `ControlEligibility`, the reducer, the HUD, and the service stay unchanged; the new Mac surface is one listener and one poster in the executable. The direct candidate widens `ControlEligibility` with a second admission API, an input source type, remote pairing maps, and a second queue consumer.

Grafted from the direct candidate:
- **Release on background.** The iOS controller sends key up for every held key on scene phase changes to background and on disconnect, not only on gesture cancellation.
- **Wire shape.** Typed `RemoteKey` plus `RemotePhase` enums parsed once at the boundary; both candidates agree. Keep the synthetic candidate's bounded newline-delimited JSON frames.

Corrections to the base:
- **Listener lifecycle follows the app, not the tap.** #47 requires advertising whenever Monitor Volume runs. Start the listener at launch, stop it on sleep and termination, restart it on wake unconditionally. Do not gate it on `interceptor.open` succeeding: when the tap is not open, a posted event simply reaches macOS, which is the pass-through rule.
- **Single connection.** The listener accepts one TCP connection at a time; a new connection replaces the old one after releasing its held keys. This bounds the same-key interleaving risk below, matching the one-iPhone product.
- **Verification surface.** Per the build research (#44), `make test` and `make check` gain the iOS simulator steps instead of separate `ios-test` and `ios-check` targets, so one command surface still covers both apps; `make ios-ipa` is the only new target. The iOS deployment target must allow the installed simulator runtimes (iOS 26.2 and 26.5 observed with `xcrun simctl list runtimes`), while the requester's device runs iOS 27.0.1.

Rejected from the direct candidate: `ControlEligibility.admitRemote`, `InputSource`, `RemoteInputID` pairing maps, and the coordinator-owned remote queue consumer. They exist only to give remote input its own admission path, which #47 makes unnecessary. Per-source key pairing is the one real advantage lost (see risks).

Agreement, no decision needed: both candidates chose a committed Xcode project for the iOS app consuming a local Foundation-only Swift package (`Shared/MonitorRemoteProtocol`, iOS and macOS platforms) shared with the Mac executable, and both rejected XcodeGen and Tuist because a generator would become a required build dependency. No new dependency is introduced.

## Risks carried into the spec

1. **First implementation step, a probe:** confirm that an NX_SYSDEFINED subtype-8 event posted by Monitor Volume reaches its own session event tap, is parsed and routed unchanged, and that a passed-through synthetic event changes the macOS system volume with the native OSD. Run it with the Accessibility grant in place (never revoked). If it fails, the fallback is the direct candidate's admission path plus an explicit pass-through implementation, and #47's rule must be re-checked.
2. **Same-key interleaving:** `ControlEligibility` pairs key down and up by `MediaKey` only (`Sources/MonitorVolumeCore/Domain/ControlEligibility.swift:239-263`). A physical key and a remote key held at the same moment for the same command can pair the wrong release. Accepted as negligible for one user with one iPhone at a desk; bounded by the single connection and by releasing held keys on disconnect.
3. **Unauthenticated listener:** per #45, any device on the network can post the three keys through Monitor Volume. Record this in an ADR during the spec if it passes the ADR necessity gate.
4. **Repeat cadence and per-press latency** are unmeasured; the spec fixes the cadence and the device check measures latency.
