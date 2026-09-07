# ADR 0002: Replace the native volume OSD on macOS Tahoe

- Status: Accepted
- Date: 2026-09-04
- Tracking issues: [#5](https://github.com/taekwondodev/ProArtVolume/issues/5), superseded feedback contract in [#26](https://github.com/taekwondodev/ProArtVolume/issues/26)

## Context

ProArt Volume routes Apple volume keys to the active ASUS PA279CV. The original decision required DDC-confirmed feedback rather than the unrelated Core Audio value. Issue #26 explicitly supersedes confirmed-only content and presentation: accepted input owns immediate requested-intent feedback, while hardware confirmation remains internal and visually silent.

The initial implementation loaded the private `OSD.framework` dynamically and invoked `OSDManager` with `showImage:onDisplayID:priority:msecUntilFade:filledChiclets:totalChiclets:locked:`. Runtime introspection on macOS 26.5 reported the method encoding `v48@0:8q16I24I28I32I36I40B44`, which matches the Objective-C call ABI used by the adapter.

The private API historically accepted either a percentage pair such as 35 filled chiclets out of 100 or a rounded classic scale such as 6 out of 16. Current MonitorControl source retains both forms in `MonitorControl/Support/OSDUtils.swift`.

Neither form produces an accurate volume value on macOS Tahoe. Testing the installed Release artifact showed that every confirmed unmuted DDC volume rendered as a full volume bar, while mute rendered as empty. A diagnostic build changed only the OSD graphic to brightness and supplied 4 filled chiclets out of 16. That build rendered a half-filled brightness bar, proving that the app's OSD call was visible while also showing that Tahoe no longer follows the supplied classic total. Restoring the volume graphic restored the full bar independently of the confirmed DDC value.

This behavior agrees with public compatibility reports:

- [MonitorControl](https://github.com/MonitorControl/MonitorControl) documents that on macOS Tahoe the native Control Center OSD appears, but its percentage value does not show or update.
- [MonitorControl issue #1782](https://github.com/MonitorControl/MonitorControl/issues/1782) records that the Tahoe private OSD framework does not provide the value functionality required for external display control.
- [BetterDisplay issue #4602](https://github.com/waydabber/BetterDisplay/issues/4602) describes the native Tahoe OSD as having limited functionality with no proper value output.

The selector belongs to a private framework with no supported Apple contract. Its presence and matching ABI do not guarantee that supplied external values affect rendering.

## Decision

Keep the private `OSD.framework` adapter removed. Present the non-activating app-owned SwiftUI HUD immediately for accepted input after eligibility has been established from a trustworthy hardware seed. Do not wait for command read-back.

The HUD chooses the pointer screen at burst presentation, with main-screen fallback, then keeps placement stable. It displays the configured monitor name, requested percentage or mute state, a matching speaker symbol, and a proportional bar. The panel does not accept input or activate ProArt Volume. Hardware success, failure, and recovery never correct or reopen it.

Create the panel only when needed, reuse it across rapid input, and release it after dismissal. Accepted input restarts the one-second inactivity baseline; boundary input pulses content without restarting entrance. Reduce Motion removes scale while retaining opacity. Do not retain the inaccurate native OSD as a fallback.

## Consequences

The OSD represents ordered user intent without transport delay and is not coupled to an undocumented renderer that reads unrelated Core Audio state. It is not a guarantee that a pending or uncertain hardware write succeeded.

The app owns the HUD's visual fidelity, placement, accessibility, lifecycle, and compatibility. Its design should remain restrained and use adaptive system materials and symbols rather than imitating private implementation details.

The HUD adds a short-lived AppKit panel and SwiftUI view. Historical disposable Release measurements were 0.0 percent idle CPU and upper-bound resident-memory increases of 10.72 MiB hidden and 11.67 MiB visible. These are not measurements of the issue #26 implementation. The new lifecycle silently observes permission changes, releases the OSD after dismissal, and introduces no helper process.

Future macOS releases may provide a supported API that can represent external values. Reintroducing a system-owned OSD requires runtime proof that it renders supplied external intent accurately, not only proof that a selector can be invoked. No native timing equivalence or numerical latency SLA is established by this decision.