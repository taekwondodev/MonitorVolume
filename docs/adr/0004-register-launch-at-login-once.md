# ADR 0004: Register launch at login once on first launch

- Status: Accepted
- Date: 2026-09-12
- Tracking issue: [#37](https://github.com/taekwondodev/ProArtVolume/issues/37)
- Supersedes: the login-registration prohibition in [#19](https://github.com/taekwondodev/ProArtVolume/issues/19); the remaining lifecycle contract stays in force

## Context

ProArt Volume is an invisible media-key utility. Without a login item, it is unavailable after a new macOS login until the user launches it manually. The product has no menu-bar item, Dock presence, settings surface, onboarding, or management window that could host an app-owned login preference.

Issue #24 verified on the target Mac that `SMAppService.mainApp` can register the signed installed application, launch it at the next login, and unregister it. macOS exposes the resulting state in System Settings. Issue #37 selected automatic registration on the first launch after the feature ships, with one absolute attempt even when the API fails.

The login item and the app's persistent marker cannot be changed transactionally. Ordering must therefore choose between risking a repeated registration attempt and risking no system call after an interruption.

## Decision

The application Handler invokes login registration after its existing launch diagnostics, observers, and media-key reopening path have started. Login registration does not determine Accessibility or hardware eligibility.

A private `UserDefaults` marker records that the registration attempt has been consumed. When the marker is absent, the Handler sets it, synchronizes the preference write, and then calls `SMAppService.mainApp.register()`. Registration is attempted without consulting the current service status, and errors are ignored. When the marker is present, every later launch is a no-op for login registration.

Marker-first ordering intentionally prefers at-most-once behavior. An interruption after the marker is persisted but before the Service Management call may leave the app unregistered. The app does not retry, report the failure, request approval through custom UI, or open System Settings.

macOS remains the only management surface. If the user disables ProArt Volume under Login Items, the app does not re-enable it. There is no helper, agent, daemon, toggle, notification, or recovery flow for registration.

## Alternatives rejected

- Register on every launch or reconcile from `SMAppService.status`: this could override a system-owned disable choice.
- Retry until registration succeeds: this contradicts the selected single-attempt contract.
- Record the marker only after success: an error would cause a later retry.
- Add a first-run prompt or settings toggle: this would expand the invisible product surface for one system-owned preference.

## Consequences

A successful first attempt makes ProArt Volume available after later logins. A failed, denied, interrupted, or approval-blocked attempt is permanent unless the private marker is changed outside the product flow. This is an accepted tradeoff, not a recovery feature.

The synchronous Service Management call runs only once and only after the existing runtime lifecycle has been established. `UserDefaults.synchronize()` is retained specifically to complete the marker write before crossing the external Service Management boundary; ordinary preference reads and writes elsewhere should not copy this exceptional use.

Verification uses the signed installed Release app. Issue #37 observed an absent marker and login item become an enabled login item on first launch, then observed that unregistering and relaunching left it disabled. The final installed state was restored to enabled. A fresh logout/login was not repeated for #37 because issue #24 had already proved next-login launch on the target Mac.
