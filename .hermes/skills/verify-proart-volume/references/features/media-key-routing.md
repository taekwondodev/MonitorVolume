# Media-key routing

## Public entry point

Press volume up, volume down, or mute while the installed app is running.

## Automated proof

`make test` proves the typed routing policy consumes only the three approved keys while the target output is active, consumes only matching key-up events, passes inactive and unrelated events through, applies saturating five-point changes, aggregates repeats without overlapping DDC writes, drops cancelled intents before repository access, and makes no DDC call while inactive.

`make check` proves the Release app builds with complete strict concurrency and the event tap requests only the system-defined event mask.

## Manual proof

On the real Mac, grant Input Monitoring and Accessibility from the panel. With the PA279CV selected as the default output, confirm each volume key changes hardware and shows the app-owned Tahoe-style OSD on the screen containing the pointer only after read-back. Confirm the percentage and bar match the confirmed volume, mute shows an empty bar and muted label, and rapid repeated keys refresh the same non-activating HUD. Select another output and confirm the same keys retain normal macOS behavior without showing the app-owned HUD. Revoke either permission and confirm panel controls remain usable while the permission explanation appears.
