# ADR 0001: Defer multi-display target binding until hardware is available

- Status: Deferred
- Date: 2026-09-03
- Tracking issue: [#10](https://github.com/taekwondodev/ProArtVolume/issues/10)

## Context

ProArt Volume must read and write only the configured ASUS PA279CV. `MonitorIdentity.target` is the source of truth for its stable EDID identity.

The current DDC transport finds the exact framebuffer through those stable fields, then selects an external `DCPAVServiceProxy` according to the recursive IORegistry traversal order. The proxy exposes that it is external but does not directly expose the monitor EDID identity. Multiple external displays can therefore make target binding ambiguous.

The observed single-display IORegistry topology does not place `DCPAVServiceProxy` below the matching `AppleCLCD2` framebuffer. Therefore, the proposed shortcut of searching only the framebuffer's descendants is not supported by current evidence. A stronger association needs evidence from a real multi-display topology rather than an assumed parent-child relation.

Active-output detection has a related limit. `CoreAudioOutputRepository` currently matches the default output by configured model name, the manufacturer held by `MonitorIdentity.target`, and DisplayPort transport. Core Audio does not currently bind that device to the stable EDID identity used by the DDC path.

The required multi-display hardware is not currently available for investigation.

## Decision

Defer the multi-display binding design until the second display is available. Keep the current single-external-display behavior unchanged in the meantime.

No multi-display safety architecture is selected by this ADR. In particular, it does not approve traversal-order matching, framebuffer-descendant matching, display-name matching, or ordinal matching as the durable solution.

## Constraints for the future decision

- A write must never be sent to a display whose identity has not been tied unambiguously to the configured PA279CV.
- Ambiguity must fail closed rather than selecting a likely display.
- DDC control identity and Core Audio active-output identity must describe the same physical display.
- The design must be derived from observed identifiers and topology with both displays connected.
- Investigation starts read-only. Hardware writes begin only after target binding is proven, and each write must be reversible.
- Runtime evidence must contain only target-relevant identifiers, not unrelated device inventory.
- Repository boundaries remain unchanged unless evidence demonstrates that a different ownership model is required.

## Evidence to collect

With both displays connected, capture the minimum target-relevant data needed to answer these questions:

1. Which IORegistry properties or registry-entry relationships remain stable while either display is connected, disconnected, or reordered?
2. Can the exact EDID framebuffer be correlated with one DCP endpoint or service proxy without relying on global traversal order?
3. Which Core Audio properties can correlate the default output with the same physical display?
4. Does the mapping remain stable across relaunch, sleep and wake, cable reconnection, and port changes?
5. When the mapping is ambiguous, can the app detect that state before opening a DDC service?

Use a read-only probe first. Exercise reversible writes only after the probe identifies one unique target in every tested permutation.

## Consequences

The current configuration remains supported without speculative transport changes. Multi-display safety remains an explicit unresolved risk until the tracking issue is grilled with real hardware evidence. The future implementation may introduce a fail-closed state or a stronger end-to-end identity, but that choice belongs to the later investigation and grilling session.
