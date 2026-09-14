# ADR 0005: Rename the product to Monitor Volume

- Status: Accepted
- Date: 2026-09-14
- Tracking issue: [#8](https://github.com/taekwondodev/ProArtVolume/issues/8)

## Context

The shipped name ProArt Volume names an ASUS monitor family. The app routes volume keys to whichever external monitor is the current default audio output, including volume-only targets that are not ProArt displays. A visitor or user who reads the bundle name therefore infers a brand-limited product.

The identifier `dev.taekwondodev.ProArtVolume` is the TCC and Login Item identity. Changing it drops the Accessibility grant and the previous login registration. System Settings remains the only management surface for leftover entries.

## Decision

The product identity and Swift package are Monitor Volume. The bundle name, executable name, identifier `dev.taekwondodev.MonitorVolume`, install path `~/Applications/Monitor Volume.app`, package and target names, source and test directory names, import statements, logger subsystem, and default-output dispatch queue label all follow that identity.

The transport target keeps its name. Its C symbol prefix changes from `PAV` to `MV` because `PAV` spelled the former product name.

The build path assembles and installs the renamed app first, then stops the legacy process, removes the legacy bundle, and verifies that it is gone. A failed compile, sign, or install leaves the legacy app in place. The removal is a no-op once the legacy bundle is absent.

Losing the Accessibility grant and re-attempting login registration are accepted consequences. The grant is re-granted once. Any leftover Login Item or Accessibility entry for the former app is removed by the user in System Settings.

## Alternatives rejected

- Keep the ProArt name and explain the broader binding in the README: the OS-visible name would still claim a single brand.
- Preserve the bundle identifier while renaming the display name: TCC would stay, but the package, executable, and documents would disagree with the product.
- Rewrite earlier decision records and git history to the new name: those records describe the product as it was decided.

## Consequences

A rebuild after this change is a new app to macOS. Volume keys do not route until Accessibility is granted again. Login registration runs its first-attempt contract against the new identifier.

Earlier ADRs keep the former product name as written. The GitHub repository path is unchanged.

## Conditions for reconsideration

Revisit if a second identity must coexist with the former bundle, or if a notarized distribution requires a stable identifier from this point forward.

## Evidence

Issue #8 records the identity list, the stop-uninstall-install order, and the accepted TCC and login consequences.
