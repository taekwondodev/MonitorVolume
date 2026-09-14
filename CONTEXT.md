# Monitor Volume

Monitor Volume routes macOS volume input to the external monitor selected as the default audio output while leaving ordinary system volume behavior available for other destinations.

## Language

**Target monitor**:
The single physical external monitor resolved for the active audio destination and bound to the current control session.
_Avoid_: Active monitor, primary monitor, any audio monitor

**Active audio destination**:
The macOS default audio output when it resolves uniquely to one target monitor.
_Avoid_: Connected monitor, visible display

**Control session**:
One generation-bound association of a target monitor's identity, display name, capabilities, and confirmed hardware state.
_Avoid_: Current monitor, selected display

**Volume-only target**:
A target monitor with confirmed DDC volume support and an explicit unsupported mute response. Volume keys are controlled; mute input remains with macOS.
_Avoid_: Broken mute, software-muted monitor

**Multi-display configuration**:
A hardware configuration in which the target monitor and at least one other external display are connected concurrently.
_Avoid_: Multi-monitor support
