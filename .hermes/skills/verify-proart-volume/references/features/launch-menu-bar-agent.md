# Launch menu-bar agent

The user can open the real application bundle and the menu-bar agent remains running.

## Public path

Launch Services opens the assembled `.app` bundle whose executable is the SwiftPM product declared in `Package.swift`.

## Drive

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py prove
```

The helper uses a unique bundle, identifier, build directory, and run directory.

## Proof

The exact executable inside the prepared bundle remains alive after launch. The helper writes `.hermes/verification/evidence/<run-id>/launch.json`, terminates only the owned PID, removes scratch state, and confirms that evidence remains readable.

## Gotchas

This proves bundle launch and process lifetime, not visual placement of the status item. Launch Services is shared by the current macOS user session.
