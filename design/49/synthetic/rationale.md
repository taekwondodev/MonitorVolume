# Synthetic key ingress candidate

## Problem

Issue #49 adds an iPhone remote while preserving one fail-closed policy for physical and remote media keys. The existing macOS event tap parses system-defined media-key events and `ControlEligibility.route(_:)` owns admission, key-pair consumption, and pass-through; its caller then updates the HUD and submits the command. The candidate converts remote key phases into the same system-defined events, leaving that path unchanged. The app remains one accessory process and the iPhone remains an unsigned SideStore app. Relevant current boundaries are `Sources/MonitorVolume/Handler/MediaKeyInterceptor.swift:149-180`, `Sources/MonitorVolume/Handler/MediaKeyEventParser.swift:15-35`, `Sources/MonitorVolumeCore/Domain/ControlEligibility.swift:239-263`, and `Sources/MonitorVolume/Handler/ApplicationCoordinator.swift:272-280`.

## Usage (caller's view)

The companion imports only the local wire module, not macOS core or transport APIs. On iOS, the composition root makes one client:

```swift
let remote = RemoteController()
remote.start()
// SwiftUI observes remote.status; buttons are enabled only when connected.
```

A button owns a press lifetime. Each sent down/repeat maps to a media key down and release sends up:

```swift
.remoteButton(.volumeUp) {
    remote.press(.volumeUp)       // send down
} onRepeat: {
    remote.repeatPress(.volumeUp) // send another down while held
} onRelease: {
    remote.release(.volumeUp)    // send up, including cancellation
}
```

The Mac app creates one listener beside its existing lifecycle coordinator and binds it to the synthetic event poster:

```swift
let ingress = RemoteCommandListener(poster: SystemMediaKeyPoster())
coordinator.attachRemoteIngress(ingress)
// coordinator starts/stops ingress with app launch, sleep, wake, and termination.
```

The iPhone status view maps the controller's single status value to the persistent label and Settings action:

```swift
Text(remote.status.label)
Button("Open Settings") { remote.openLocalNetworkSettings() }
    .opacity(remote.status == .localNetworkDenied ? 1 : 0)
```

## Shape

### Module map

```text
Package.swift (existing macOS SwiftPM, unchanged platform and targets)
Sources/MonitorVolume/Remote/
  RemoteCommandListener.swift     NWListener, per-connection framing, lifecycle
  SystemMediaKeyPoster.swift      NX_SYSDEFINED CGEvent construction/post
  RemoteServiceAdvertiser.swift   Bonjour service metadata for NWListener
Shared/MonitorRemoteProtocol/     small standalone Swift package target
  RemoteCommand.swift             version, key, phase domain values
  LineCodec.swift                 private Codable newline frame conversion

ios/MonitorRemote.xcodeproj/      committed minimal Xcode project
  App/                            SwiftUI app, controller, discovery, UI
  Info.plist                      local-network and Bonjour declarations
```

The shared package contains only portable command semantics and frame encoding. It excludes Network.framework, CoreGraphics, AppKit, UI state, discovery, and monitor-domain types. A committed Xcode project is the lightest dependency-free route: it directly references the shared package source through a local package dependency and has no generator installation/version contract. SwiftPM continues to own the macOS executable and test surface.

### Type sketch

`RemoteCommand` is one complete wire operation. Down frames repeat while held, with a final up; no client identifier, authentication, or monitor state is sent. The listener binds each accepted TCP connection to its own pairing state so a disconnect cannot leave a key down. Framing and version validation occur at the network boundary; malformed frames close only that connection. There is deliberately no shared mutable protocol writer state.

```swift
// Shared/MonitorRemoteProtocol/Sources/MonitorRemoteProtocol/RemoteCommand.swift
public enum RemoteKey: String, Codable, Sendable { case volumeUp, volumeDown, mute }
public enum RemotePhase: String, Codable, Sendable { case down, up }

/// One versioned command; each JSON value occupies one newline-terminated frame.
public struct RemoteCommand: Codable, Equatable, Sendable {
    public let version: UInt8
    public let key: RemoteKey
    public let phase: RemotePhase
    public init(key: RemoteKey, phase: RemotePhase) { /* not implemented */ }
}

public enum RemoteLineCodec {
    public static func encode(_ command: RemoteCommand) throws -> Data { /* not implemented */ }
    /// Decode only a complete UTF-8 line, reject unknown versions and oversized input.
    public static func decode(line: Data) throws -> RemoteCommand { /* not implemented */ }
}
```

```swift
// Sources/MonitorVolume/Remote/SystemMediaKeyPoster.swift
import CoreGraphics

/// Produces the NX_SYSDEFINED subtype-8 event understood by MediaKeyEventParser.
@MainActor final class SystemMediaKeyPoster {
    func post(_ command: RemoteCommand) { /* TODO encode keycode/state into data1; post HID-system-state event */ }
}

// Sources/MonitorVolume/Remote/RemoteCommandListener.swift
@MainActor final class RemoteCommandListener {
    private let poster: SystemMediaKeyPoster
    private var listener: NWListener?
    private var connections: [UUID: RemoteConnection] = [:]

    init(poster: SystemMediaKeyPoster) { /* not implemented */ }
    /// Idempotent. Advertise the one versioned service; each accepted connection gets private parser/pair state.
    func start() { /* TODO create TCP listener, publish Bonjour service, accept connections */ }
    /// Idempotent. Cancel listener and connections; release held synthetic keys before return.
    func stop() { /* TODO release each connection's down keys, cancel all NW objects */ }
}

private struct RemoteConnection {
    var receiveBuffer: Data
    var heldKeys: Set<RemoteKey>
}
```

The key invariant is at-most-one outstanding down per key per connection. A repeated down is posted as another down for the existing repeat behavior. An up is posted only for a held key. On cancellation/disconnect, synthesize up for held keys. `ControlEligibility` itself tracks consumed keys by `MediaKey`, not remote connection; therefore the adapter must serialize synthetic phase delivery on the main actor and must not pretend client-specific ownership exists in core. This design assumes one companion client at a time; a second simultaneous client can interleave with a physical held key and is an implementation risk requiring a runtime proof or explicit single-client enforcement.

```swift
// Sources/MonitorVolume/Handler/ApplicationCoordinator.swift (new surface)
@MainActor func attachRemoteIngress(_ listener: RemoteCommandListener) { /* not implemented */ }
// launch: start after lifecycle observers; sleep: stop before sleep invalidation;
// wake: start only after existing revalidation/open succeeds; termination: stop before teardown.
```

```swift
// ios/MonitorRemote/App/RemoteController.swift
@MainActor @Observable final class RemoteController {
    private(set) var status: RemoteStatus = .searching
    private let browser: RemoteBrowser
    private let connection: RemoteConnectionClient
    func start() { /* TODO browse, connect, observe path/errors, publish status */ }
    func press(_ key: RemoteKey) { /* not implemented */ }
    func repeatPress(_ key: RemoteKey) { /* not implemented */ }
    func release(_ key: RemoteKey) { /* not implemented */ }
    func openLocalNetworkSettings() { /* not implemented */ }
}

enum RemoteStatus: Equatable {
    case connected, noMacFound, notOnWiFi, localNetworkDenied
    var label: String { /* not implemented */ }
}

@MainActor final class RemoteBrowser { /* NWBrowser lifecycle; reconnect on path and wake */ }
@MainActor final class RemoteConnectionClient {
    func send(_ command: RemoteCommand) { /* encode, serialize writes on this connection */ }
}
```

The SwiftUI view owns gesture lifetime and schedules repeats; its cancellation path always releases. Haptics are a button-level effect after a command is accepted for send, not protocol state. Discovery/connection are hidden behind the observable controller. This keeps the three-button view from coordinating transport internals. The listener owns transport framing and converts validated commands directly to the poster, so the flow is connection -> listener -> poster -> existing tap -> parser -> eligibility -> coordinator, within three new files. The public surface hides Bonjour, reconnect, buffering, and wire encoding. No network transport types cross into app view code.

Validation belongs at the TCP boundary: protocol version, complete line, bounded frame, key/phase enums. The poster is the only CoreGraphics adapter and deliberately emits the same keycode/state encoding the existing parser accepts (`Sources/MonitorVolume/Handler/MediaKeyEventParser.swift:25-35`). The existing tap callback and core remain untouched, including its returned-event pass-through (`Sources/MonitorVolume/Handler/MediaKeyInterceptor.swift:162-180`). Per principle-boundary-discipline, there are no extra validation guards after conversion into typed command values. Per principle-separate-before-serializing-shared-state, every connection has isolated framing and held-key bookkeeping, merged only at the event-tap boundary.

### Build surface

```make
.PHONY: ios-ipa ios-test ios-check

ios-test:
	xcodebuild test -project ios/MonitorRemote.xcodeproj -scheme MonitorRemote \
	  -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO

ios-check:
	xcodebuild build -project ios/MonitorRemote.xcodeproj -scheme MonitorRemote \
	  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO

ios-ipa:
	./scripts/build-ios-ipa.sh
```

`ios-ipa` archives for generic iOS without a signing identity, exports an unsigned IPA, and does not alter the Mac build identity or bundle metadata. Simulator test and check are isolated additions to existing commands; current `make test` and `make check` retain their mappings (`Makefile:16-23`, `Tests/Tooling/command_surface_test.py`).

## Synthesis decision

Not applicable: this is an independent Phase B candidate. The orchestrator will compare candidates and fill synthesis.

## Tradeoffs accepted

- We accept relying on macOS delivering posted synthetic system-defined events to this process's existing tap in exchange for byte-for-byte reuse of admission and pass-through behavior.
- We accept the private and platform-sensitive NX_SYSDEFINED event construction in one tiny adapter in exchange for leaving Core and the established tap unchanged.
- We accept a committed Xcode project in exchange for avoiding a generator dependency and retaining the SwiftPM macOS build.
- We accept a line-delimited JSON encoding and per-connection transient state in exchange for transparent protocol inspection and bounded parsing.
- We accept connection-scoped held-key recovery in exchange for no persistent state; app crash still relies on OS cleanup of posted keys.

## Alternatives considered

- Calling `ControlEligibility.route(_:)` directly from the listener loses because the listener would have to fabricate tap ownership and recreate callback delivery/HUD behavior; preserving pass-through to the native system volume path becomes a second control path and broadens the interface. Synthetic input hides more policy behind existing machinery.
- A generated Xcode project (XcodeGen/Tuist) loses because it adds a tool and lock/version discipline solely to create a small iOS target. It hides project-file mechanics but exposes generator availability and configuration to every developer and CI runner.
- Put Network.framework listener and wire schema in MonitorVolumeCore loses because it imports transport concerns into the core and breaches the existing platform boundary. The executable adapter keeps core untouched and the portable wire package has a smaller contract.

## Open questions and risks

- Can the system event tap observe a synthetic NX_SYSDEFINED event posted by this same process with the chosen post location and source fields, without looping or being filtered?
- Can two event sources send down/up for the same key concurrently without `ControlEligibility.consumedKeyDowns` pairing the wrong release, given its set is keyed only by `MediaKey` (`Sources/MonitorVolumeCore/Domain/ControlEligibility.swift:98-99,239-260`)?
- Should the listener enforce a single TCP connection, since the product describes one phone and core pairing has no connection identity?
- Does a newline JSON frame provide sufficient bounds and compatibility expectations for this intentionally unauthenticated local network protocol?
- Which concrete iPhone simulator runtime is installed in CI, and should the project use a generic destination plus a separately discovered simulator for tests?

## Next implementation step

Build a minimal macOS-only probe that posts each media-key phase and records whether the unchanged event tap parses and routes it, before implementing the listener or iOS UI.
