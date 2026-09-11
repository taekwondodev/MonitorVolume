# Consented installed A/B comparison

## Public entry point

Validate the frozen contract with `make issue33-protocol`. Set `ISSUE33_A_WORKTREE` and `ISSUE33_B_WORKTREE` to the clean, pinned live-candidate worktrees and run `make issue33-doctor`. These commands are read-only apart from local build artifacts and do not install or launch the app.

Prepare a new campaign directory with `scripts/issue33-live.sh prepare`. Preparation builds each strict-concurrency Release executable once, derives distinct Candidate A and Candidate B metadata from the unchanged production manifest, assembles and signs each final bundle once, and retains the signed bundle, source closure, metadata and executable hashes, designated requirement, protocol, runner, and environment probe. Preparation refuses an existing destination, dirty worktrees, or a ref mismatch. It does not install or launch any app.

Each campaign directory is immutable evidence. A failed ordinal is retained without replacement, and a campaign with a failed mandatory ordinal cannot become a selection campaign. Start a new directory for a procedural rerun. Reuse installed candidates only when the new manifest validates them as byte-identical, non-symlinked, manifest-bound bundles, then obtain a new setup receipt and fresh readiness for both identities.

## Consent gate

Setup and collection have separate session-scoped consent. Do not invoke `make issue33-setup` without exact consent for installation/launch and manual Accessibility changes. Setup installs both retained candidates at their distinct paths, launches them sequentially through LaunchServices for one manual grant each, and requires a fresh candidate-bound readiness attestation. It never changes TCC or requests physical input. Do not invoke `scripts/issue33-live.sh run` until the user separately consents to the selected workload. Run consent categories must exactly match that workload; normal, lifecycle/sleep-wake, and stress scopes remain separate. Consent does not persist between sessions.

Before every run, keep a Terminal window ready with:

```sh
ISSUE33_CAMPAIGN_DIR=<campaign> make issue33-stop
```

This inspects both candidate identities, revalidates any running candidate against its manifest-bound bundle, executable, metadata, and designated requirement, and stops only those exact candidate processes. It never signals the production app or an unknown or modified artifact. Use it immediately if keyboard or pointer input is disrupted. The collector never synthesizes input, changes permissions, starts sleep/wake, adds a watchdog, or automatically relaunches.

## Drive

Measured runs never build, sign, install, or change permissions. Before each run the collector revalidates both installed candidate bundles, proves the production app and both candidates stopped, launches only the scheduled candidate through LaunchServices, and verifies exactly one selected executable-path owner. A one-shot readiness record must bind the candidate, bundle identifier, actual executable hash, source ref, PID, lifecycle generation, Accessibility trust, active tap ownership, and successful current-generation Service validation before resource sampling or any operator prompt begins.

Runs are serial and hold the campaign lock end to end. Execute one ordinal at a time. After readiness, focus the runner Terminal and let the operator read the frozen instruction, type `START`, perform the action, wait at least the stated minimum, type `DONE`, and finally type `USABLE` only when ordinary keyboard and pointer input remained usable. Do not proxy these acknowledgements through chat or another mediated channel while lifecycle instrumentation is active.

After the runner exits, validate the retained report and manifest digest and prove Candidate A, Candidate B, and production all have zero processes before starting the next ordinal. Continue after an isolated failed run only when evidence is preserved, cleanup converges to zero, and ordinary input remains safe. Stop on input disruption or a systematic apparatus failure that would invalidate later runs.

Normal input sequences are balanced to restore starting volume and mute intent. Stress and lifecycle runs remain separate. If a disabled-tap event does not occur naturally, record it unavailable rather than inducing an unsafe stall.

## Evidence

Each run retains the readiness attestation, raw `proc_pid_rusage` samples plus `proc_pidinfo` thread counts and process-start identity, parent-monotonic phase boundaries, power/low-power/thermal/host/toolchain observations, unified lifecycle log, final capacity/occupancy/accounting, installed latency trace, callback and event-delivery-proxy metrics, executable/source/protocol/runner bindings, operator observations, and both full and publishable reports. The minimal readiness record is identical in full and inactive modes and ends before measured phases; inactive mode still forbids detailed lifecycle and latency evidence. Unified-log loss or malformed framing, incomplete callback pairs, unbalanced tap resources, process/hash/identity mismatch, missing phase samples, environment drift, or cleanup failure fail closed. Missing setup, readiness, mandatory runs, metrics, or retained failed runs produce an explicit inconclusive analysis without replacement.

Full instrumentation has a fixed 65,536-record lifecycle budget. `budgetExhausted`, a missing session end, or an unfinished operation or query pair makes the trace incomplete even when the app appeared responsive. Keep operator interaction direct and close to the frozen phase minima. Do not widen the budget further or weaken completeness checks to accommodate a slow control channel.

The publishable projection removes local paths and process identifiers. Visual OSD observations remain manual. Callback event-to-entry timing includes upstream delivery and is not relabeled as pure run-loop latency.

## Cleanup and isolation

Normal run completion asks the selected app to quit normally, then verifies all three known app identities have zero processes. Failure cleanup uses the campaign-bound stop and preserves the failed report. After final evidence capture or explicit abandonment, `make issue33-cleanup` requires the operator to record manual removal of both Accessibility entries, proves zero processes, removes only byte-identical manifest-bound Candidate A and B bundles, reads back their absence, and verifies the production bundle is unchanged. Evidence survives cleanup.

The macOS user session, two candidate Accessibility identities, event tap, and physical DDC channel are shared. The production path and identity remain outside campaign ownership. Do not run another app build, verification campaign, monitor tool, deliberate load, production app, or second candidate in parallel.
