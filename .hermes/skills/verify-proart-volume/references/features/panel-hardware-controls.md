# Panel hardware controls

The popover exposes a bounded volume slider and a hardware mute toggle for the exact PA279CV.

## Public path

Open the installed app, select its menu-bar item, drag the volume slider, or change the Mute switch.

## Drive

The slider accepts whole values from 0 through 100 and submits its final value when editing ends. The mute switch maps only to DDC VCP `0x8D` values `1` and `2`. Both commands pass through the `VolumeControlService` actor and the same DDC Repository used by the runtime probe.

## Proof

`ProArtVolumeRuntimeProbe --verify-controls` reads the current hardware state, writes the same volume and mute values, and requires exact read-back for both. Service tests cover serialization, latest-volume coalescing, read-back mismatch, write failure, and preservation of the last confirmed state. A human confirms the installed slider, mute switch, and visible error presentation.

## Gotchas

The same-value runtime proof verifies command transport without altering the user's audio setting. Do not replace hardware mute with volume zero, and do not publish an intended value before DDC read-back confirms it.

The panel control path has no media-key permission dependency and does not request Accessibility or Input Monitoring access. The same-value proof is side-effecting at the DDC protocol level even though it converges to the existing hardware values.
