<p align="center">
  <img src="Resources/Media.xcassets/AppIcon.appiconset/Monitor%20Illustration%20v2.png" width="128" alt="Monitor Volume icon">
</p>

<h1 align="center">Monitor Volume</h1>

<p align="center">Route macOS volume keys to the external monitor selected as the default audio output.</p>

## What it is and how it works

Monitor Volume is a Swift 6.2 SwiftPM accessory app for macOS 15 and later. It has a C transport shim, a core library, and an executable. It is an `LSUIElement` app: no Dock icon and no menu bar item. Feedback is a non-activating SwiftUI HUD.

A CoreGraphics event tap intercepts Volume Up, Volume Down, and Mute. That tap requires the Accessibility grant. Volume and mute travel as DDC/CI over I2C through the private `IOAVService` entry points, resolved at runtime with `dlopen`. The macOS default audio output is resolved to exactly one framebuffer. Eligibility is fail-closed: if the destination is missing, ambiguous, or not a controllable external monitor, the keys stay with macOS.

Those private entry points have no Apple contract. The default-output binding is recorded in [ADR 0001](docs/adr/0001-follow-default-monitor-audio-output.md). The app-owned HUD, rather than the private Tahoe OSD, is recorded in [ADR 0002](docs/adr/0002-replace-native-volume-osd-on-macos-tahoe.md).

## iOS Companion

```bash
make ios-ipa
```

The command builds `.build/ios/MonitorRemote.ipa`. With it, the iPhone raises, lowers, and mutes the volume while it is on the same Wi-Fi as the Mac and the Monitor Remote app is open. The app lets go of the Mac when it moves to the background and reconnects when it is opened again.

### Install with SideStore

The companion is installed with [SideStore](https://sidestore.io/) and a free Apple Account; no Apple Developer Program membership is needed.

After `make ios-ipa`, move `.build/ios/MonitorRemote.ipa` to the iPhone (AirDrop or Files), then open it in SideStore, which signs it with your Apple Account.

## Performance

Idle measurements of the installed Release app on Mac14,9, macOS 27.0 build 26A428, arm64. Physical footprint is the quantity Activity Monitor displays, not RSS.

<p align="center">
  <img src="docs/performance/idle.svg" alt="Idle CPU, physical footprint, and installed bundle size">
</p>

The numbers come from `make profile`. They are not a historical HUD record.

## Build

```bash
make build
```

The Makefile builds, signs, installs, and launches `Monitor Volume` in `~/Applications`. With an Apple Development identity installed, the Accessibility and Local Network grants survive rebuilds; with the ad hoc fallback, macOS may ask for both again after each rebuild.

## Profiling

```bash
make profile
```

The command measures the installed Release app at idle: CPU percent after discarding the unpaired first sample, physical footprint, and installed bundle size. It refuses to measure when the installed app is not the live process. It writes `docs/performance/idle-baseline.json` and regenerates the chart above. A missing baseline fails the renderer; it never substitutes a value.
