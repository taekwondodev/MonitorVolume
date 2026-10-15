# Module map: synthetic key ingress

```text
ios/MonitorRemote.xcodeproj
  MonitorRemote app target (SwiftUI, Network.framework, UIKit)
      imports MonitorRemoteProtocol
      owns remote status, discovery, connection, hold/repeat gesture, haptics
          |
          | versioned TCP command frames
          v
MonitorVolume executable (existing SwiftPM target)
  Sources/MonitorVolume/Remote
    RemoteCommandListener -> per-client frame/key state -> SystemMediaKeyPoster
          |
          | post system-defined key events
          v
  MediaKeyInterceptor -> MediaKeyEventParser -> ControlEligibility -> ApplicationCoordinator

Shared/MonitorRemoteProtocol (portable local Swift package)
  RemoteKey, RemotePhase, RemoteCommand, bounded line codec
```

## Ownership boundaries

- The shared module owns the only wire representation and its version/framing codec. It does not expose Network framework types or MonitorVolumeCore domain objects.
- The iOS app owns user interaction and client reconnect policy. It has one `RemoteController` observable surface; SwiftUI does not own NW objects.
- The macOS executable owns listener lifecycle and adapts validated messages into system key events. `ApplicationCoordinator` starts the listener only while active, stops it before sleep and termination, and restarts after successful wake/open.
- The existing event tap, parser, `ControlEligibility`, HUD, service, and `MonitorVolumeCore` are not modified. `MediaKeyInterceptor` continues deciding consume versus pass-through.
- The listener's parser buffer and held-key set belong to one connection. Connections are not merged into common mutable connection state. Because downstream key pairing lacks source identity, concurrent clients remain disabled until implementation proves safe; simplest initial listener accepts one connection.

## Project layout

```text
Shared/MonitorRemoteProtocol/Package.swift
Shared/MonitorRemoteProtocol/Sources/MonitorRemoteProtocol/RemoteCommand.swift
ios/MonitorRemote.xcodeproj/project.pbxproj
ios/MonitorRemote/App/MonitorRemoteApp.swift
ios/MonitorRemote/App/RemoteController.swift
ios/MonitorRemote/App/RemoteBrowser.swift
ios/MonitorRemote/App/RemoteConnectionClient.swift
ios/MonitorRemote/App/RemoteButtonsView.swift
ios/MonitorRemote/Info.plist
Sources/MonitorVolume/Remote/RemoteCommandListener.swift
Sources/MonitorVolume/Remote/SystemMediaKeyPoster.swift
scripts/build-ios-ipa.sh
```

The Xcode project is committed, not generated. A local Swift package gives the iOS target the exact same codec definitions as macOS without making SwiftPM build the iOS app or introducing a generator. The package is macOS/iOS portable Foundation-only; macOS production package remains macOS 15 as declared in `Package.swift:5-9`.
