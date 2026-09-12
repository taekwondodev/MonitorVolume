# ADR 0001: Accept verified multi-display target binding

- Status: Accepted
- Date: 2026-09-03
- Tracking issue: [#10](https://github.com/taekwondodev/ProArtVolume/issues/10)

## Context

ProArt Volume must read and write only the configured ASUS PA279CV. `MonitorIdentity.target` is the source of truth for its stable EDID identity.

The current DDC transport finds the exact framebuffer through those stable fields, then selects an external `DCPAVServiceProxy` according to the recursive IORegistry traversal order. The proxy exposes that it is external but does not directly expose the monitor EDID identity. Multiple external displays can therefore make target binding ambiguous.

The observed single-display IORegistry topology does not place `DCPAVServiceProxy` below the matching `AppleCLCD2` framebuffer. Therefore, the proposed shortcut of searching only the framebuffer's descendants is not supported by current evidence. A stronger association needs evidence from a real multi-display topology rather than an assumed parent-child relation.

Active-output detection has a related limit. `CoreAudioOutputRepository` currently matches the default output by configured model name, the manufacturer held by `MonitorIdentity.target`, and DisplayPort transport. Core Audio does not currently bind that device to the stable EDID identity used by the DDC path.

On 2026-09-12, the target PA279CV and a second audio-capable external display were observed together. Core Audio reported the PA279CV as the default output with the configured name, manufacturer, and DisplayPort transport. The IORegistry traversal contained the non-target framebuffer and proxy on `dispext0`, followed by the target framebuffer and proxy on `dispext1`. A read-only probe that reproduced `PAVCreateTargetService` selected the `dispext1` proxy on five consecutive scans. Disconnecting and reconnecting either display recreated the corresponding proxy, preserved the same `dispext0` and `dispext1` association, and produced the same target selection on five scans after each reconnection. Swapping the two external connections recreated both proxies and again preserved the association and target selection on five scans. Sleep and wake also preserved the association and target selection on five scans, kept the PA279CV as the default output, and left the installed signed application running as expected. A reversible Volume Down and Volume Up check after each topology change affected only the PA279CV, confirming the selected proxy end to end. This disproves ambiguity in the observed two-display topology, both individual reconnection cases, the connection-swap case, and sleep and wake. It does not establish behavior for an enumeration order that differs from the one observed on this Mac. The topology probe itself did not open a DDC service or send hardware commands.

## Decision

Keep the current traversal behavior unchanged. Accept its residual dependency on IORegistry enumeration order because every topology change exercised on the target Mac preserved the correct association and every end-to-end check controlled only the configured PA279CV.

Do not add speculative binding logic without a reproduced failure. Reopen the decision if a future topology selects the wrong proxy or cannot select the target unambiguously.

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

The tested two-external-display configuration selects the expected proxy across every exercised topology change without additional transport code. An unobserved IORegistry enumeration order could still violate the assumed pairing. That risk is accepted for this personal utility and does not justify a speculative implementation.
