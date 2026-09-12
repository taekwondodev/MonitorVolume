# ADR 0001: Follow the default monitor audio output

- Status: Accepted
- Date: 2026-09-12
- Tracking issue: [#38](https://github.com/taekwondodev/ProArtVolume/issues/38)

## Context

ProArt Volume previously bound Core Audio eligibility and DDC operations to one compiled PA279CV identity. Selecting the T16KB as the macOS default audio output therefore returned media-key handling to macOS even though that display supports DDC volume control. The two displays differ in capability: the PA279CV supports volume and mute, while the T16KB explicitly reports mute VCP 0x8D as unsupported.

The selected Core Audio DisplayPort output exposes a display name and manufacturer. The IORegistry framebuffer exposes the corresponding product name, manufacturer, product ID, and optional serial, followed by its external DCP service proxy in the verified topology.

## Decision

Resolve the macOS default DisplayPort audio output to exactly one framebuffer by manufacturer and product name. Accept either an exact product-name match or the space-delimited product-name suffix exposed by Core Audio on the target hardware. Use the framebuffer's product ID and optional serial as the DDC identity. Fail closed when no matching framebuffer, more than one matching framebuffer, or no associated external DCP proxy is present.

Bind the resolved identity, display name, capabilities, confirmed state, and generation into one control session. Every queued intent, read, and write carries that session identity. Re-resolve the default output immediately before every write, and discard work when its generation or identity is no longer current.

Treat mute support as a domain capability rather than as a failed all-or-nothing monitor read. Only the explicit DDC unsupported-command result marks mute unsupported while preserving the confirmed volume. Malformed and transient responses retain bounded recovery. Volume-only sessions admit volume key pairs and pass both mute phases through to macOS without a custom OSD or mute write.

Retain the verified IORegistry framebuffer-to-proxy traversal and its residual dependency on enumeration order. A write must never target a display whose identity is not tied unambiguously to the selected audio destination; ambiguity fails closed.

## Consequences

Changing the default audio output requires no app configuration or rebuild. The existing OSD uses the session's display name. The PA279CV retains five-point volume steps, mute, and unmute-on-volume behavior; the T16KB receives volume operations only.

The implementation is intentionally not universal monitor certification. Indistinguishable displays, non-DisplayPort paths, and unobserved IORegistry topologies fail closed or remain out of scope. Runtime verification still requires both observed monitors to be connected and selected in turn.
