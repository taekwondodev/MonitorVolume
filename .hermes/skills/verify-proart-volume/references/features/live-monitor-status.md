# Live monitor status

The popover distinguishes the exact PA279CV as active, inactive, unavailable, malformed, or unreadable.

## Public path

Open the installed app through Launch Services and select its menu-bar item.

## Drive

The DDC adapter matches manufacturer `AUS`, product `10088`, and alphanumeric serial `R5LMTF117048`, then reads VCP `0x62` and `0x8D`. The Core Audio adapter compares the default output's name, manufacturer, and DisplayPort transport.

## Proof

The runtime skill executes `ProArtVolumeRuntimeProbe`, which compiles against the same Domain, Service, and Repository target as the app. It must return confirmed JSON with bounded volume, mapped mute, active or inactive output, and exact same-value read-back for volume and mute. The installed popover requires visual confirmation that it presents the same state.

## Gotchas

`IOAVService` and CoreDisplay are non-public Apple interfaces. This local app is not suitable for Mac App Store distribution. Do not substitute a display index or transient UUID for the stable identity fields.