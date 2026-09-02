# Popover presentation

The user can select the menu-bar item and see the ProArt Volume popover.

## Public path

The `MenuBarExtra` composition root lives in `Sources/ProArtVolume/ProArtVolumeApp.swift`; its content lives in `Sources/ProArtVolume/Handler/MonitorStatusView.swift`.

## Drive

No automated public drive exists yet. Launch the real bundle, select its menu-bar item, and inspect the popover manually.

## Proof

Current gap: a human confirms that the popover opens, displays live monitor status, and exposes the bounded volume and mute controls.

## Gotchas

Hardware values shown by the panel remain last-confirmed values when a command fails.
