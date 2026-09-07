# Media-key routing

## Public entry point

Press volume up, volume down, or mute while the installed app is running.

## Automated proof

`make test` covers supported-event decoding and pairing, ordered saturated five-point intent, mute parity, boundary unmute, complete-state coalescing, stale generations, failure discard, serialized I/O, and controlled read-only recovery. These tests do not exercise the actual event tap or renderer.

`make check` checks strict-concurrency Release compilation and tooling. `make measure-latency` installs and arms opt-in executable-bound evidence; `make latency-report` validates distinct input, intent, presentation/draw, and hardware stages. Schema 1 is historical confirmed-feedback evidence; schema 2 is the input-intent contract. Draw completion means `NSHostingView.draw` returned, not physical scanout or a frame for every key press.

For an archived schema-1 baseline, call `scripts.latency_report.build_latency_report(trace, original_executable_path, archived_executable=archive_path)`. The original path must still match raw metadata; the archived bytes must match its SHA256. The report labels this binding `historical_archive`, never current installed proof. Keep raw metadata unchanged and the current bundle installed. Ordinary reporting has no archive argument and still requires the actual installed bytes. Compare recomputed summaries with the preserved report, and state workload and sample-count differences instead of claiming a controlled speedup.

## Manual proof

Grant Accessibility through the native path and select the configured PA279CV output. Accepted input immediately displays requested intent, without waiting for DDC. Test isolated/mixed rapid keys, mute parity, muted volume input, 0/100 boundaries, and input during dismissal. One burst keeps its pointer-screen placement and panel, restarts a one-second inactivity timer, and pulses boundary content without re-entering. Reduce Motion removes scale, retaining opacity.

Observe no hardware-driven correction, reopening, error OSD, or prompt during recovery. Before trusted readiness, after permission loss, and on an inactive target, new keys pass through with no app OSD or deferred replay. Consumed events are never reinjected. Matching key-up remains consumed while the tap remains available.

Use installed traces to demonstrate a completed draw while prior DDC work is still in progress. Compare first-draw and convergence separately against the stored baseline linked from issue #26. No numerical SLA or native equivalence is claimed. The user judges continuous placement, proportional bar, restrained motion, and lack of flicker; these remain manual checks.
