# Capability Map

| Capability | Public entry point | Proof |
| --- | --- | --- |
| [Launch menu-bar agent](launch-menu-bar-agent.md) | Open `ProArt Volume.app` through Launch Services. | The exact bundle executable remains alive and evidence survives cleanup. |
| [Menu-bar icon](menu-bar-icon.md) | Observe the system menu bar after launch. | Current gap: requires visual confirmation. |
| [Popover presentation](popover-presentation.md) | Select the ProArt Volume menu-bar item. | Current gap: requires visual confirmation. |
| [Live monitor status](live-monitor-status.md) | Open the popover while the target monitor is connected. | The runtime skill records the shared Service/Repository result; presented state requires visual confirmation. |
| [Panel hardware controls](panel-hardware-controls.md) | Use the installed volume slider or Mute switch. | Same-value hardware writes and read-back are automated; SwiftUI gestures and error presentation require visual confirmation. |
