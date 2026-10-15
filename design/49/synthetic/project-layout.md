# Project layout sketch

Use a committed, minimal `ios/MonitorRemote.xcodeproj`, no generator. Its single iOS app target references `Shared/MonitorRemoteProtocol` as a local Swift package. The package exports Foundation-only `RemoteKey`, `RemotePhase`, `RemoteCommand`, and `RemoteLineCodec`, with macOS and iOS platform declarations. The existing root SwiftPM package remains macOS-only and gains the local package as a dependency of its executable target when appropriate; no iOS target is added to that manifest.

```text
Package.swift                         existing macOS package, add protocol dependency
Shared/MonitorRemoteProtocol/
  Package.swift                        iOS 17+, macOS 15+, one library product
  Sources/MonitorRemoteProtocol/
    RemoteCommand.swift                domain wire envelope + private codec

ios/MonitorRemote.xcodeproj/
  project.pbxproj                      committed project, one app target/scheme
  xcshareddata/xcschemes/MonitorRemote.xcscheme
  App/MonitorRemoteApp.swift
  App/RemoteController.swift
  App/RemoteBrowser.swift
  App/RemoteConnectionClient.swift
  App/RemoteButtonsView.swift
  Info.plist                           NSLocalNetworkUsageDescription,
                                       NSBonjourServices
Sources/MonitorVolume/Remote/
  RemoteCommandListener.swift          NWListener, connection-local buffers
  SystemMediaKeyPoster.swift           system-defined media key event adapter
scripts/build-ios-ipa.sh               unsigned archive/export
```

The iOS source has no access to `MonitorVolumeCore`; the Mac executable has access to it as it does today. The wire package is an explicit portable contract, not a public re-export of networking or core types. The root `Package.swift` remains macOS 15+ (`Package.swift:5-9`).

`make ios-check` builds the simulator destination without signing. `make ios-test` runs protocol and controller tests on a simulator. `make ios-ipa` creates an unsigned IPA through Xcode archive/export, with no Developer Program identity; SideStore handles bundle identifier rewriting. These commands are additive to existing `make test` and `make check` (`Makefile:16-23`).
