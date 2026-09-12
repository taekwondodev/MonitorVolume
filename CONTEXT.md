# ProArt Volume

ProArt Volume routes macOS volume input to one configured external monitor while leaving ordinary system volume behavior available when that monitor is not the active audio destination.

## Language

**Target monitor**:
The single physical external monitor that ProArt Volume is allowed to control.
_Avoid_: Active monitor, primary monitor, any audio monitor

**Active audio destination**:
The macOS default audio output when it represents the target monitor.
_Avoid_: Connected monitor, visible display

**Multi-display configuration**:
A hardware configuration in which the target monitor and at least one other external display are connected concurrently.
_Avoid_: Multi-monitor support
