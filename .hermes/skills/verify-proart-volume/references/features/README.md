# Capability Map

| Capability | Public entry point | Proof |
| --- | --- | --- |
| [Invisible lifecycle](invisible-lifecycle.md) | Open or reopen the installed app; grant/revoke Accessibility; change output or wake. | Bundle/process checks are automated. Native permission visibility, login launch, invisible UI, and lifecycle behavior remain live/manual checks. |
| [Media-key intent and OSD](media-key-routing.md) | Press volume up, volume down, or mute. | Domain/Service tests and executable-bound traces complement manual OSD and pass-through acceptance. |
| [Offline shared contract](offline-comparison.md) | Run `make offline-contract`. | Release Swift Domain/Service conformance, suspension/admission/recovery scenarios, and CPU/RAM apparatus; native framework and installed-app performance remain unavailable. |
| [Hardware proof](hardware-proof.md) | Explicitly invoke the isolated proof driver. | Real volume/mute transitions and restoration, structured failed outcomes, and durable evidence. Never part of ordinary verification. |
