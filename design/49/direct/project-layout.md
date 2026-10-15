# Project and module map

## Repository layout

```text
Package.swift
Sources/
  MonitorTransport/                 # existing C shim and IOKit boundary
  MonitorVolumeCore/                # existing Mac domain, service, repositories
  MonitorRemoteProtocol/             # new wire message values and codec only
  MonitorVolume/                      # existing accessory executable, listener adapter
Tests/
  MonitorVolumeTests/                 # existing Mac/core tests
  MonitorRemoteProtocolTests/         # protocol codec tests, SwiftPM
  MonitorVolumeTests/                 # add direct admission pairing tests
MonitorVolume.xcodeproj/              # committed native project
  Companion/                          # iOS SwiftUI shell and RemoteClient
  CompanionTests/                      # simulator unit tests
```

MonitorVolume.xcodeproj references the local Swift package's `MonitorRemoteProtocol` product. It must not link `MonitorVolumeCore`, `MonitorTransport`, AppKit, or IOKit into iOS. Keep the Mac executable and signing flow in SwiftPM/scripts unchanged. A committed Xcode project is one source-controlled target manifest, not a second Mac build definition.

## Ownership and flow

```text
Remote TCP bytes -> RemoteCommandListener -> RemoteMessageCodec -> typed command
                                                    -> ControlEligibility.admitRemote
                                                    -> single admitted FIFO
Physical CGEvent -> parser -> ControlEligibility.route -> same FIFO
                                                       -> main-actor coordinator consumer
                                                       -> reducer -> HUD -> IntentControlService
```

Remote not-admitted result ends at the listener. It does not post or synthesize any CGEvent. Physical `.passThrough` returns the original event from the CG tap callback. Each accepted remote TCP connection receives a fresh `RemoteInputID`; disconnect removes only that connection's held-key pairing. Listener lifecycle belongs to `ApplicationCoordinator`: launch starts, sleep and termination stop, wake starts if not stopped. Calls are idempotent.

The iOS `RemoteClient` owns browser, connection, reconnection and status; SwiftUI owns only rendering and button gestures. `MonitorRemoteProtocol` owns versioned command encoding/decoding and no transport framework objects. Mac listener and iOS client are the only framework adapters.

## Build surface sketch

```make
.PHONY: ios-test ios-check ios-ipa

ios-test:
	@xcodebuild test -project MonitorVolume.xcodeproj -scheme Companion -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO

ios-check:
	@xcodebuild build -project MonitorVolume.xcodeproj -scheme Companion -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO

ios-ipa:
	@xcodebuild -project MonitorVolume.xcodeproj -scheme Companion -configuration Release -archivePath .build/Companion.xcarchive archive CODE_SIGNING_ALLOWED=NO
	@xcodebuild -exportArchive -archivePath .build/Companion.xcarchive -exportOptionsPlist packaging/SideStoreExportOptions.plist -exportPath .build/ios-ipa
```

The export options and archive packaging must be verified against the chosen Xcode and SideStore expectations before implementation. Simulator targets require no device, developer account, or signing. `make test` and `make check` remain authoritative Mac checks; their changes should add simulator test/build steps without replacing strict-concurrency Release checks or current tooling tests.
