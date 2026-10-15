# iOS companion build and signing research

Scope: native iOS companion sends Volume Up, Volume Down, and Mute to the Mac on the same Wi-Fi. The phone does not display volume or mute state. This report is research, not an implementation plan for the network protocol.

## Findings

### 1. SwiftPM and project layout

**Facts.** This repository's Swift package declares macOS 15 as its only platform and vends an executable product backed by an executable target. Its existing app is explicitly described as a SwiftPM macOS accessory app (Package.swift:5-12, README.md:11). SwiftPM targets compile source into modules or test suites, while its product/target model is not an Xcode iOS application target or app bundle (Apple Target documentation: https://developer.apple.com/documentation/packagedescription/target). Xcode documents app projects, schemes, archives and physical-device run destinations; its official workflow builds/runs an app on a simulator or paired physical device (https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices; https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases).

**Inference.** SwiftPM remains appropriate for the current command-line-driven macOS executable and reusable code, but it does not replace the Xcode app target required for a normally installable signed iOS .app. The viable shapes are:

- **Committed Xcode project/workspace:** Xcode owns native targets, schemes, signing settings and destinations. This is the direct, tool-free-at-build-time choice; project-file maintenance is committed repository state. Apple documents Xcode projects and schemes as the app build/run mechanism (https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices).
- **Generated project (XcodeGen or Tuist):** commit the declarative specification and generation instructions, generate Xcode project files, then use Xcode/xcodebuild. XcodeGen describes itself as a command-line Xcode project generator (https://github.com/yonaskolb/XcodeGen; https://github.com/yonaskolb/XcodeGen/blob/master/Docs/ProjectSpec.md). Tuist documents a declarative project manifest and generation/build/test workflows (https://tuist.dev/en/docs/guides/features/projects). This adds a generator installation/version to the build contract.
- **Xcode app project consuming a local Swift package:** keep an Xcode iOS app target, add this repository (or a dedicated package subdirectory) as a local package dependency, and import its library product. Xcode's package integration is the intended route for packages used by app projects (https://developer.apple.com/documentation/xcode/adding-package-dependencies-to-your-app). The present package cannot be consumed unchanged as iOS-capable because it declares only macOS and contains macOS-only modules/framework dependencies (Package.swift:7-19; README.md:11-13).

### 2. Shared module

**Facts.** `MonitorVolumeCore` is already a SwiftPM target and the Mac executable depends on it (Package.swift:21-27). The current key mapping has Volume Up, Volume Down, and Mute cases in `MediaKey`, mapped to `MediaKeyCommand` (Sources/MonitorVolumeCore/Domain/MediaKey.swift:1-21). Those declarations use `package` access, not `public` access, so they are visible within this package but are not a public API for a separate Xcode app target importing the package (Sources/MonitorVolumeCore/Domain/MediaKey.swift:1-21).

**Inference / recommendation.** Put the wire message schema and platform-neutral command enum in a small shared SwiftPM library target/product whose declared supported platforms include iOS and macOS. Let the Mac executable and the Xcode iOS app both depend on that same local package product. Keep sockets, discovery, UI, and macOS DDC logic outside this shared module. Expose types with suitable public access when they cross the package boundary. Do not make the iPhone consume the Mac's `MonitorVolumeCore` wholesale: the present core depends on `MonitorTransport`, whose linker settings include IOKit (Package.swift:14-24). A dedicated wire-protocol module minimizes platform reach and makes the bytes/types contract one shared implementation.

### 3. Repository command surface

**Facts.** `make test` runs `swift test`; `make check` delegates to `scripts/check.sh`; `make build` and `make verify` delegate to app-specific scripts; `make clean` only runs `swift package clean` (Makefile:16-32). The command-surface test asserts those mappings and explicitly guards that clean does not delete Applications or `.app` bundles (Tests/Tooling/command_surface_test.py:36-53). `check.sh` invokes `app_tool.py check`; build and verify invoke corresponding app_tool subcommands (scripts/check.sh:1-4; scripts/build-app.sh:1-4; scripts/verify-installed-app.sh:1-4).

**Inference / recommendation.** Preserve the existing macOS meanings. Extend `make test` with a deterministic `xcodebuild test` invocation for an iOS Simulator destination/scheme, and `make check` to build/test relevant iOS targets without signing assumptions. Add explicit `ios-build`, `ios-install`, and likely `ios-verify` targets rather than changing `make build` (which today installs and launches the Mac app in `~/Applications`, per README.md:27-33). `make verify` should remain Mac-specific or become an umbrella while preserving the exact current Mac verification. Update `Tests/Tooling/command_surface_test.py` to assert every new target's documented invocation and preserve the clean safety assertion; avoid making default `make test` require a connected phone, paid signing, or provisioning. The `devicectl` install command needs a built, signed `.app` path and a selected device (observed syntax below).

### 4. Local signing and iPhone installation

**Observed local facts.** Command `security find-identity -v -p codesigning` output:

```text
1) 61879E2654A43ED3FDFE50F6BE3CA2D2BD8AD460 "Apple Development: Davide Galdiero (Z4W47W7NW7)"
     1 valid identities found
```

This proves an Apple Development identity is installed. It does not establish whether its team is paid or a Personal Team. `profiles status -type enrollment` output was `Enrolled via DEP: No` and `MDM enrollment: No`; this is device-management status, not Apple Developer Program membership. `find "$HOME/Library/MobileDevice" -maxdepth 3 -type f -print` produced no listed files. `find /Library/MobileDevice/Provisioning Profiles -maxdepth 1 -type f -print` reported that directory does not exist. Thus there was no local provisioning profile to inspect for team or expiry. `xcodebuild -version` output was `Xcode 27.0` and `Build version 27A266a`. `xcrun devicectl list devices` showed `iPhone taekwondodev`, UDID `00008120-000915403458201E`, `available (paired)`, model iPhone 14 Pro (iPhone15,2), physical.

**Documentation facts.** Apple states that a Personal Team permits on-device testing but has 7-day expiry for registered App IDs, device registrations and provisioning profiles; the profile requires rebuilding/reinstalling after expiry. It permits up to 10 App IDs, 3 devices and 3 apps per device. (https://developer.apple.com/help/account/basics/about-your-developer-account). Apple states distribution to registered devices, TestFlight, or the App Store requires Apple Developer Program membership (https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases). Apple also documents that Xcode registers a physical device and creates a provisioning profile the first time the app runs there (https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices).

**Inference and prerequisites.** The existing identity is enough to establish that Xcode can attempt development signing, but not enough to prove team membership, profile availability, or that this iPhone has been registered for the selected team. First configure/check the Apple Account and Team in Xcode Settings > Accounts, then let Xcode automatic signing create a profile and register this already-paired phone, or register it through the paid program team. A paid program is not a prerequisite for personal on-device development testing; it is required for the documented device distribution/TestFlight/App Store routes. With a Personal Team, expect the 7-day provisioning expiry and repeat build/install. If longer-lived registered-device distribution or TestFlight is wanted, the requester must join an Apple Developer Program team and register the iPhone. Do not infer paid membership from the certificate's display name.

**Observed command interface.** `xcrun devicectl device install app --help` says it installs an app bundle with `.app` extension and gives usage `xcrun devicectl device install app --device <uuid|...> <path>`. For this paired device, the shape is `xcrun devicectl device install app --device 00008120-000915403458201E /path/to/Companion.app`. `xcrun devicectl device process launch --help` documents launch by bundle identifier or path. No app was built or installed during this research, so successful signing/install is not observed.

## Unresolved limits

- The Apple account's membership status/team role was not directly inspected, and no provisioning profile exists locally to reveal a TeamIdentifier, profile type, or expiry. Check Xcode Accounts / Developer portal with the account owner.
- No iOS project, simulator build, provisioning operation or physical installation was attempted. The command syntax is verified from local help, not an end-to-end install.
- The recommendation assumes the shared model can be separated without exposing monitor-specific state to iOS. The phone's required one-way command-only behavior remains as given scope; no state-return channel is proposed here.

## Coordinator verification

- Confirmed `package` access on `MediaKey`, `MediaKeyCommand`, `MediaKeyPhase`, and `MediaKeyEvent` (Sources/MonitorVolumeCore/Domain/MediaKey.swift:1-32) and the Makefile mappings (Makefile:16-32).
- The provisioning search above missed the current Xcode location. `~/Library/Developer/Xcode/UserData/Provisioning Profiles` does not exist either, so no profile is installed locally.
- Xcode's cached team metadata conflicts for the same team `6STK5CF75S`. `defaults read com.apple.dt.Xcode IDEProvisioningTeamByIdentifier` reports `teamType = "Personal Team"` and `isFreeProvisioningTeam = 1`; the legacy key `IDEProvisioningTeams` reports `teamType = Individual` and `isFreeProvisioningTeam = 0`. Paid membership therefore remains unconfirmed; the requester can confirm it at https://developer.apple.com/account.
