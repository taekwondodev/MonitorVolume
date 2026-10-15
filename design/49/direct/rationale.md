# Direct admission ingress

## Problem

Monitor Volume currently admits physical media-key events in `ControlEligibility.route(_:)`, consumes matched releases, queues accepted downs, and delivers them to a main-actor coordinator that reduces intent, shows the HUD, and submits one service request. A remote command must use that exact eligibility and delivery pipeline, but must not impersonate an operating-system key or rely on the event tap being reentrant. The tap is also deliberately the mechanism that returns an unroutable physical event to macOS. This candidate gives remote commands their own admission entry point while leaving physical pass-through untouched. The project must additionally gain a native iOS app without a generator dependency or changing the Mac app's existing build/signing surface.

## Usage (caller's view)

The iOS app imports only `MonitorRemoteProtocol` and sends typed commands; it knows nothing about Mac monitor eligibility or DDC. The Mac composition root owns one listener and one existing coordinator pipeline.

```swift
// iOS button: a completed tap sends a down/up pair; repeat sends repeated pairs.
try await connection.send(.command(.volumeUp, .down))
try await connection.send(.command(.volumeUp, .up))

// Mac ingress: the listener parses wire bytes before calling this domain API.
let admission = eligibility.admitRemote(.volumeUp, phase: .down, from: peer)
await coordinator.handle(admission)

// Physical tap retains its OS-specific pass-through decision.
switch eligibility.route(parsedEvent) {
case .passThrough: return event
case .consumeKeyDown(let delivery), .consumeKeyUp: return nil
}
```

The real remote path does not expose `PeerID`, wire messages, or transport framing to core callers. The public domain shape below uses a remote source token only to pair releases per connection. It returns a domain decision, not a framework event. The coordinator delivers admitted downs to the same reducer, HUD, and service code used by physical keys. Remote unsupported/unavailable commands are explicitly rejected by admission and the listener sends no OS event; this is the meaning of pass-through for remote input: it remains unhandled by Monitor Volume, while macOS cannot receive an event that never originated there.

## Shape

Keep the committed Xcode project for the iOS app and the existing Swift package for macOS. Add a small shared `MonitorRemoteProtocol` SwiftPM target, with only versioned message-domain types and strict encode/decode at the network boundary. The project references the local package for that product. This avoids XcodeGen/Tuist as a new required build tool, preserves SwiftPM's existing Mac checks, and lets simulator builds compile the companion against exactly the same protocol. The shared target has no AppKit, SwiftUI, Network.framework, CoreAudio, or monitor-control dependency.

`ControlEligibility` owns admission policy and key-pairing state. Physical `route(_:)` requires active tap ownership, eligible session, and command support; remote `admitRemote(_:phase:from:)` requires only eligible session and command support. Both enqueue `AdmittedMediaKey` on downs and both return an admission decision. Physical down keys are keyed by `MediaKey`; remote held keys are keyed by `(RemoteInputID, MediaKey)`, so disconnect cleanup can release that peer's pairing without clearing physical state. Repeated downs are admitted as repeated commands, consistent with current held-key volume stepping. A down that was passed through does not create a pairing, so its up also passes through. `removeRemoteInput(_:)` clears only that input's consumed-key pairing.

The shared admission queue is drained by the existing main-actor `MediaKeyInterceptor` consumer for physical events, and by one coordinator-owned consumer for remote events. Both dequeue from the single ordered queue, so there is one owner and no duplicated reducer/HUD/service path. The queue remains the point where callback-thread admission crosses to main actor. The coordinator starts a listener at launch, stops it on sleep and termination, restarts idempotently on wake, and removes each remote input's pairing on connection cancellation. Startup/stop are desired-state operations: repeated start/stop converge.

The listener receives bytes, decodes `RemoteMessage` at the boundary, maps valid commands to domain `MediaKey` and phase, admits them, and does not manufacture CGEvents. For a command that cannot be routed, it returns a typed `notAdmitted` result to the connection policy; the listener deliberately does not fall back to system volume because remote input has no native event to pass through. For admitted downs, the coordinator's single queue consumer calls one `handle(_:)`; it reduces intent, shows HUD, and submits to service exactly as current `mediaKeyInterceptor(_:received:)` does (current call site: `Sources/MonitorVolume/Handler/ApplicationCoordinator.swift:272-280`).

On iOS, a `RemoteClient` owns NWBrowser/NWConnection, reconnection and path changes; a small SwiftUI model maps connection state to the four persistent labels and disables buttons unless connected. A button press sends down then up; a gesture repeat sends repeated downs, and cancellation/disappearance sends up for every currently held command. The wire decoder accepts down/up only. Haptics occur at local send initiation, not on Mac acceptance, since the protocol has no acknowledgement contract.

Interface depth is concentrated in `ControlEligibility.admitRemote` (stateful eligibility, support, pairing, and queue admission behind one domain call) and `RemoteListener` (browse/connection lifecycle and framing behind a small app-facing lifecycle). The coordinator is the one intentional integration point; it does not know TCP framing. Boundary decoding validates protocol version and message shape once; internal handlers receive typed domain values, per principle-boundary-discipline. Distinct physical and remote pairing sets prevent either actor from erasing the other's release state, per principle-separate-before-serializing-shared-state. Input source is represented only where needed for remote per-connection pairing, rather than threading a generalized source abstraction through every call site, per principle-laziness-protocol.

### Type sketch

See `types.swift`, `ios.swift`, and `project-layout.md`. Signatures and `not implemented` bodies are the contract. Existing types `MediaKey`, `MediaKeyPhase`, `AdmittedMediaKey`, and `InputAdmissionDecision` are reused; `AdmittedMediaKey` gains source metadata only if diagnostics require it. Wire messages remain private to the protocol target and are parsed into domain values at the listener boundary.

## Synthesis decision

This is a single candidate proposal, not an arena synthesis. It chooses direct admission ingress, a committed Xcode project consuming the local Swift package, and a shared wire-only protocol target. No other candidate was available to compare in this runner.

## Tradeoffs accepted

- We accept a committed Xcode project and its maintenance burden in exchange for no generator dependency and straightforward simulator/Xcode workflows.
- We accept a remote-specific admission entry point in exchange for preserving physical tap ownership and making remote commands independent of synthetic event behavior.
- We accept that unroutable remote commands produce no system volume change in exchange for never forging a system input or surprising users with fallback behavior.
- We accept shared FIFO delivery for physical and remote admitted commands in exchange for one ordering boundary and one coordinator-side reducer/HUD/service path.
- We accept a small per-connection held-key set in exchange for correct down/up pairing and isolated disconnect cleanup.

## Alternatives considered

- Post synthetic NX_SYSDEFINED events and let the existing tap process them. This superficially minimizes API changes, but exposes callers to event construction, tap reentrancy, and source-identification details, and cannot robustly distinguish injected events from physical input. It also makes pass-through semantics dependent on OS event behavior.
- Give the listener its own reducer and submit directly to the service. This reduces the coordinator integration but duplicates stateful intent policy and risks different HUD and ordering semantics. Its public surface hides little because callers must still coordinate reducer, presenter, and service.
- Generate an Xcode project from a manifest. This removes checked-in project repetition but makes the generator a required contributor/CI dependency and adds another authoritative build description beside Package.swift.

## Open questions and risks

- Should the wire protocol acknowledge admission, or is local connected/send status sufficient for the initial four-state UI?
- Should the listener bind to all local interfaces as required by same-Wi-Fi discovery, or constrain interface selection while preserving Bonjour reachability?
- Does an iOS gesture reliably emit cancellation when the app backgrounds, and must the model send releases on scene phase changes as well as gesture cancellation?
- Does the shared FIFO require a bounded queue policy under a remote flood, and what observable drop behavior is acceptable?
- Can the simulator-only check and test run on the repository's minimum supported Xcode without signing or local network entitlements?

## Next implementation step

Add typed remote admission and pairing tests to `ControlEligibility` first, then wire a single remote queue consumer into the existing coordinator before adding Network.framework and iOS UI shells.
