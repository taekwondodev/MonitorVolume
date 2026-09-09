# Candidate-bound offline apparatus

## Public entry point

Run `make offline-contract` from the repository root with `ISSUE32_CANDIDATE`, `ISSUE32_WORKTREE`, `ISSUE32_SOURCE_REF`, and a new `ISSUE32_EVIDENCE_DIR`. Optional `ISSUE32_WORKLOAD`, `ISSUE32_INSTRUMENTATION`, and `ISSUE32_RUN_ORDINAL` values select one frozen single-candidate gate. The command has no A/B comparison mode.

## What it proves

The opt-in `ProArtVolumeIssue32Conformance` executable enters through the selected candidate's real `CandidateBinding → MediaKeyInterceptor` post-parse seam. Its report covers:

- latched suspension for permission, tap-disable, creation, and overflow reasons;
- explicit reopen after old-owner tap teardown;
- sleep/wake fencing and fresh Service validation;
- bounded FIFO admission, key pairing, rejection, and discard bookkeeping;
- intent boundary/parity examples and stale-delivery rejection;
- observed candidate topology from executed scheduling boundaries;
- named normal-use and stress phases separated in the raw evidence;
- executable, source-closure, driver, compiler, and frozen-configuration bindings.

The parent samples `proc_pid_rusage` every 10ms, retaining instantaneous resident size and cumulative nanosecond user-plus-system CPU time. It derives interval CPU utilization from consecutive cumulative values over the parent monotonic interval; never use `ps` lifetime-average `%CPU` as a phase metric. Every attempt is retained as sampled, failed, or censored. The child synchronously appends phase-boundary records; the parent timestamps their observation and each resource poll with its own `time.monotonic_ns()` clock. Total and per-phase summaries must reconstruct exactly from those parent-domain records, every phase must contain a sample and a wholly-contained CPU interval, and the original child `DispatchTime` timestamp remains attached for audit. No callback-duration SLA is defined; unavailable native observations are explicitly labeled.

The parent runner refuses an existing output directory and persists `report.json`, `raw-samples.jsonl`, raw stdout/stderr, `binding.json`, phase events, the exact executable, and the exact frozen collection protocol. The collection-protocol SHA-256 participates in the configuration digest and must match the retained file. Phase records include exact input, pass-through, delivery, admission, rejection, discard, overflow, completion, peak-outstanding, and pending accounting; the gate rejects missing fields and broken accounting identities. Use `control --mode repeatability` for repeated same-candidate behavior and `control --mode instrumentation` for full-versus-none parity on the same candidate/workload; both exclude timestamps and resource noise. Comparative A/B collection remains a separately authorized and gated operation.

Before comparative collection, validate `scripts/issue32_collection_protocol.json` with `scripts/issue32_collection_protocol.py`. The protocol fixes the complete warmup and measured schedule, environment observation sources and build invariants, per-run sample minima and summary definitions, missing-data handling, empirical repeatability/equivalence rules, selection rules, and immediate stop conditions. Its repeatability band requires 20 valid same-candidate control runs and 19 adjacent differences per cell; its environment block names the exact power, low-power, thermal-limit, OS/toolchain, and logical-CPU observations that must be retained and matched. The validator only renders the declared schedule; it does not build, run, or compare candidates. Do not improvise run counts, ordering, exclusions, margins, or replacement runs after observing candidate results.

The only comparative executor is `scripts/issue32_collector.py`. First create a control manifest from six current apparatus reports with `validate-controls`; stale runner, matrix, protocol, source-ref, behavior, repeatability, or instrumentation evidence is rejected. Do not execute `collect` until its implementation has completed three-axis review and comparative collection is explicitly authorized. Execution is fail-closed behind `--execute-frozen-campaign`, refuses an existing output directory, builds each candidate once, and uses only hash-pinned prepared executables. Every collector-owned subprocess and apparatus auxiliary command runs in a newly owned process group; timeout cleanup terminates the group, waits the frozen grace period, and kills surviving descendants. During collection the conformance child inherits the apparatus group, so the outer watchdog covers both while the inner watchdog retains direct-child terminate-to-kill behavior. The apparatus and expected-matrix digests are pinned before preparation and rechecked around every gate. The collector observes the environment at both boundaries of every four-run block, persists atomic state and every replacement, and stops on any hard gate or drift. `analyze` accepts collected, analyzed, and inconclusive campaign states only after revalidating the current protocol, collector, apparatus, and matrix digests, then validates each selected report's recorded digest, bindings, child contract, raw reconstruction, and behavior fingerprint before deriving metrics. Its output is provisional: Candidate B remains inconclusive until the required lifecycle ownership review is green.

## What it does not prove

The offline drive never installs or launches the app bundle, changes Accessibility permissions, synthesizes system input, invokes CoreGraphics event taps, presents AppKit UI, or writes a physical monitor. Therefore it cannot prove native event-to-callback timing, tap teardown effects on system input, permission-prompt visibility, OSD draw/scanout, physical DDC transitions, native wakeups/resources, or installed-app performance. Each report names those gaps explicitly.

The resource values describe the harness process only. They are not product limits, latency SLAs, or a substitute for the later user-authorized runtime campaign.
