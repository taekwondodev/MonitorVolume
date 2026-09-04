# ADR 0002: Replace the native volume OSD on macOS Tahoe

- Status: Accepted
- Date: 2026-09-04
- Tracking issue: [#5](https://github.com/taekwondodev/ProArtVolume/issues/5)

## Context

ProArt Volume routes Apple volume keys to the active ASUS PA279CV and receives the confirmed DDC volume or mute state after each hardware command. The user-visible OSD must represent that confirmed state rather than the Core Audio output value.

The initial implementation loaded the private `OSD.framework` dynamically and invoked `OSDManager` with `showImage:onDisplayID:priority:msecUntilFade:filledChiclets:totalChiclets:locked:`. Runtime introspection on macOS 26.5 reported the method encoding `v48@0:8q16I24I28I32I36I40B44`, which matches the Objective-C call ABI used by the adapter.

The private API historically accepted either a percentage pair such as 35 filled chiclets out of 100 or a rounded classic scale such as 6 out of 16. Current MonitorControl source retains both forms in `MonitorControl/Support/OSDUtils.swift`.

Neither form produces an accurate volume value on macOS Tahoe. Testing the installed Release artifact showed that every confirmed unmuted DDC volume rendered as a full volume bar, while mute rendered as empty. A diagnostic build changed only the OSD graphic to brightness and supplied 4 filled chiclets out of 16. That build rendered a half-filled brightness bar, proving that the app's OSD call was visible while also showing that Tahoe no longer follows the supplied classic total. Restoring the volume graphic restored the full bar independently of the confirmed DDC value.

This behavior agrees with public compatibility reports:

- [MonitorControl](https://github.com/MonitorControl/MonitorControl) documents that on macOS Tahoe the native Control Center OSD appears, but its percentage value does not show or update.
- [MonitorControl issue #1782](https://github.com/MonitorControl/MonitorControl/issues/1782) records that the Tahoe private OSD framework does not provide the value functionality required for external display control.
- [BetterDisplay issue #4602](https://github.com/waydabber/BetterDisplay/issues/4602) describes the native Tahoe OSD as having limited functionality with no proper value output.

The selector belongs to a private framework with no supported Apple contract. Its presence and matching ABI do not guarantee that supplied external values affect rendering.

## Decision

Remove the private `OSD.framework` adapter and present a non-activating app-owned SwiftUI HUD after confirmed active-output read-back.

The HUD appears on the screen containing the pointer at presentation time, with the main screen as fallback. It displays the configured monitor name, confirmed percentage or mute state, a matching speaker symbol, and a proportional bar. The panel does not accept input or activate ProArt Volume.

Create the panel only when needed, reuse it across rapid confirmed updates, and release it after dismissal. Do not retain the inaccurate native OSD as a fallback.

## Consequences

The OSD can represent the DDC-confirmed monitor state accurately on macOS Tahoe and is no longer coupled to an undocumented renderer that reads unrelated Core Audio state.

The app owns the HUD's visual fidelity, placement, accessibility, lifecycle, and compatibility. Its design should remain restrained and use adaptive system materials and symbols rather than imitating private implementation details.

The HUD adds a short-lived AppKit panel and SwiftUI view. A disposable Release probe measured 0.0 percent idle CPU, an upper-bound resident-memory increase of 10.72 MiB with the panel created but hidden, and 11.67 MiB while visible. The integrated implementation avoids continuous updates and releases the panel after dismissal, so no persistent polling or helper process is introduced.

Future macOS releases may provide a supported API that can represent external values. Reintroducing a system-owned OSD requires runtime proof that it renders the supplied confirmed DDC state accurately, not only proof that a selector can be invoked.