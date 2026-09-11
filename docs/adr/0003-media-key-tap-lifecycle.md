# ADR 0003: Media-key tap lifecycle, error policy, and the revocation freeze

- Status: Accepted
- Date: 2026-09-11
- Tracking issues: [#28](https://github.com/taekwondodev/ProArtVolume/issues/28), [#34](https://github.com/taekwondodev/ProArtVolume/issues/34), [#35](https://github.com/taekwondodev/ProArtVolume/issues/35)
- Replaces the earlier ADR 0003 (shared suspension contract and offline conformance drive) and ADR 0004 (main run loop and campaign retirement). Their surviving decisions are restated here; their measurement apparatus is retired.

## Context

ProArt Volume intercepts Volume Up, Volume Down, and Mute with a CoreGraphics event tap and routes them to the ASUS PA279CV over DDC. The tap needs the Accessibility grant. While the tap is registered, every system input event waits for the app's callback to return, so the callback must stay cheap and the tap must never be left registered by a process that cannot service it.

Two questions were open: whether the tap should run on the main run loop or on a dedicated thread, and what the app should do when the grant is removed while it is running. A multi-day measurement campaign (two installed candidate identities, signed bundles, protocols, an evidence store, and a Python runner three times the size of the app) was built to answer the first question and never produced a verdict.

On 2026-09-11 the user tried both candidates by hand and captured the app's own lifecycle log with `--diagnose-input-lifecycle`. The observations below are from those runs.

## Observed facts

1. Both tap topologies behave identically when the grant is removed while the app runs: events keep arriving briefly, then mouse and keyboard freeze system-wide for several seconds, then input returns and the app receives nothing further.
2. The callback is fast throughout: entry to exit is about 30 microseconds on every recorded event, including the last one before the freeze.
3. From the moment the grant is removed, macOS stops delivering events to the tap. The app receives no callback, no error, and no notification.
4. During the freeze, `AXIsProcessTrustedWithOptions` keeps returning `true` to the app for the whole window (seven consecutive one-second polls in the captured run).
5. The distributed notification `com.apple.accessibility.api` does not fire for the revocation itself; it fires only when the Accessibility list is edited in other ways.
6. After roughly seven seconds macOS delivers `tapDisabledByTimeout`. The app removes its run-loop source and invalidates the tap within 0.5 milliseconds and enters suspension. System input recovers at that moment.
7. Replacing the installed bundle (`make build`) changes the ad-hoc signature and silently invalidates the Accessibility grant: the checkbox stays on, but the process is not trusted until the grant is toggled off and on.
8. Reopening the app from the Finder while it waits for permission does not reach `applicationShouldHandleReopen` for this accessory app with no windows; the process receives nothing. With the earlier contract (no polling while suspended, recovery only through reopen) the app could never notice a granted permission, and the only recovery was terminating and relaunching.
9. After a revocation while the tap was active, the same process keeps reading `AXIsProcessTrusted` as `true` but every later `CGEvent.tapCreate` fails. Only a new process can create a tap again.

## Decisions

### Topology

The tap stays on the main run loop. At observed parity the simpler design wins, as #28 already required. The dedicated-thread candidate is not merged and its branch is deleted.

### Error policy

Every failure the app can detect leads to the same state: release the tap, discard pending work, stay alive and inert until the user reopens the app. On reopen the app validates permission, recreates the tap, and reseeds volume and mute from the monitor's real state. Nothing is replayed.

This applies uniformly to missing permission at launch, detected revocation, tap disabled by timeout or by user input, and tap creation failure. There is no automatic retry after the system disables the tap: if macOS removed it, the app does not fight for it.

One exception, forced by fact 8: while the app waits for permission (`missingPermission` or `permissionRevoked`), it checks `AXIsProcessTrusted` once per second and reopens by itself as soon as the grant is present. Granting the permission in System Settings is therefore enough; no reopen or relaunch is needed. System suspensions (tap disabled, creation failed) do not watch for anything.

### Handoff without capacity

The callback hands accepted key-downs to the main thread through a plain FIFO. The main thread drains it within one run-loop turn, and `IntentControlService` keeps only the latest desired state, so rapid presses coalesce at the hardware boundary. The earlier admission capacity of eight, the `deliveryOverflow` suspension, and the admission metrics are removed (#35). Ordering and key-down/key-up pairing remain so that a consumed key-down never lets its key-up escape to the system.

### Revalidation

Permission is polled once per second while the lifecycle is active, outside the callback. Polling stops in suspension and sleep. Sleep discards pending work; wake revalidates only a lifecycle that was active before sleep. DDC failures are temporary Service unavailability with backoff; they never restore input eligibility by themselves.

### Verification

Verification of this utility is `make test`, `make check`, `make build`, and the user exercising the feature on the real monitor. `--diagnose-input-lifecycle` is the only diagnostic path and stays because it costs nothing when disabled and produced every fact above. A larger apparatus requires an explicit decision by the user.

## Known limitation: revocation freeze

Removing the Accessibility grant while the app has an active tap freezes system input until macOS times the tap out. The app cannot prevent this:

- it receives no signal at the moment of revocation (facts 3, 4, 5);
- it reacts within 0.5 milliseconds to the only signal it does receive (fact 6);
- the freeze window is the system's own timeout, not app latency (fact 2).

This is platform behavior for any process holding an event tap on macOS 26, and it happens only when the grant is removed while the app is running, which is not part of normal use. #34 is closed as not fixable in the app. Users who need to revoke the grant should quit the app first.

## Consequences

- After every `make build`, toggle the Accessibility grant off and on before testing (fact 7). Document this next to the build command.
- Recovery after a live revocation requires a new process (fact 9): quit and relaunch the app, then grant the permission; the app picks it up on its own.
- The measurement campaign, offline harness, latency instrumentation, hardware proof probe, and `verify-*` project skill are removed. The command surface is `test`, `check`, `build`, `verify`, `clean`.
