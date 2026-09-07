# Invisible lifecycle

## Public path

Open the installed Release bundle through Launch Services. `ApplicationCoordinator` owns launch, reopen, permission observation, output/display/sleep/wake invalidation, and termination.

## Automated checks

`make build` builds, signs, installs, and launches. `make verify` checks the signed bundle and exactly one live executable-path owner without monitor writes. Neither command proves visible prompting or absence of routine UI.

## Manual acceptance

Observe no menu-bar item, Dock presence, management window, or onboarding. With Accessibility absent, launch and explicit reopen may invoke only the native request path. Observe actual dialog visibility, since the API result cannot prove it. Grant, revoke, and regrant without relaunch; the app must silently become eligible or inactive. No Input Monitoring request or login registration is part of this contract.

Exercise user-configured macOS Login Items launch, no-monitor startup, output changes, wake and reconnect. Activity Monitor termination ends current app ownership; it does not change future Login Items choices. Ad-hoc signing can invalidate prior Accessibility authorization.

These live checks require the user's session and observations. Keep each unexercised scenario explicitly pending. ADR 0001's single-external-display limitation remains in force.
