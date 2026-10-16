# ADR 0007: Remote input as synthetic media keys from an unauthenticated LAN listener

- Status: Accepted
- Date: 2026-10-16
- Tracking issue: [#40](https://github.com/taekwondodev/MonitorVolume/issues/40), decided in the [#41 map](https://github.com/taekwondodev/MonitorVolume/issues/41)

## Decision

Monitor Volume accepts **remote input** from the iPhone **companion** over plain TCP on the local network, advertised through Bonjour, with no pairing, authentication, or encryption ([#45](https://github.com/taekwondodev/MonitorVolume/issues/45)). `RemoteCommandListener` validates each newline-delimited JSON command once, then `SystemMediaKeyPoster` posts the same system-defined media key event a physical key produces. The event tap, `ControlEligibility`, the HUD, and `MonitorVolumeCore` cannot tell remote input from a physical key, so both follow one admission rule: consumed for the target monitor, otherwise left to macOS with its own volume and OSD ([#47](https://github.com/taekwondodev/MonitorVolume/issues/47)).

The listener accepts one connection at a time and releases a connection's held keys when it closes or is replaced. It runs whenever the app runs, independent of the tap, and stops across sleep.

## Alternatives rejected

- **A direct admission API in `ControlEligibility`** ([synthesis](https://github.com/taekwondodev/MonitorVolume/blob/design/49-synthetic/design/49/synthesis.md)): input it cannot route would need a second, hand-built path to the macOS system volume without the native OSD, and the core would gain an input source type and a second queue.
- **Pairing and TLS-PSK** ([#45](https://github.com/taekwondodev/MonitorVolume/issues/45)): the home Wi-Fi is trusted, TLS-PSK was unproven on macOS 15, and pairing would add persistent UI to an invisible app.

## Consequences

- Any device on the same network can press Volume Up, Volume Down, and Mute through Monitor Volume. The exposure is bounded to those three keys; the Mac sends nothing back.
- Key pairing in `ControlEligibility` has no input source, so a physical key and a remote key for the same command held at the same moment can pair the wrong release. The single connection bounds this.
- Posting events and the tap both rely on the existing Accessibility grant. Advertising needs the macOS Local Network grant, which macOS tracks by code signature.

## Conditions for reconsideration

Revisit before adding control from outside the local network, a second remote client at once, a state channel back to the iPhone, or any input path that bypasses the event tap.
