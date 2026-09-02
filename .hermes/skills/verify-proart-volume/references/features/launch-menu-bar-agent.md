# Launch menu-bar agent

The user can open the real application bundle and the menu-bar agent remains running.

## Public path

Launch Services opens the assembled `.app` bundle whose executable is the SwiftPM product declared in `Package.swift`.

## Drive

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py prove
```

The helper delegates to the repository-owned scripts that build, install, sign, launch, verify, and stop `~/Applications/ProArt Volume.app`.

## Proof

The installed bundle has the stable expected identity and valid signature, and exactly one process owns its executable path after launch. The helper writes `.hermes/verification/evidence/<run-id>/launch.json`, delegates exact-process termination to repository tooling, and confirms that evidence remains readable.

## Gotchas

This proves bundle launch and process lifetime, not visual placement of the status item. Launch Services is shared by the current macOS user session.
