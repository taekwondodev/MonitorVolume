# ADR 0006: Measure the installed Release app at idle

- Status: Accepted
- Date: 2026-09-14
- Tracking issue: [#8](https://github.com/taekwondodev/ProArtVolume/issues/8)

## Context

The only published performance numbers were a historical HUD record, not a measurement of the current installed app. A README that asserts idle cost without a rerunnable command will drift.

Idle CPU, physical footprint, and installed bundle size are observable from the signed Release process. RSS is a different quantity on the same process. The first CPU sample has no prior reading, so pairing it as a delta invents a spike.

## Decision

`make profile` measures the installed Release app. It resolves the process by exact executable path, the same way verify and stop do, and refuses to measure when that installed app is not the live process.

The command reports idle CPU percent after discarding the unpaired first CPU sample, physical footprint as the quantity Activity Monitor displays, and installed bundle size. It writes an aggregate-only baseline and a deterministic chart derived from that baseline. It fails when the baseline is missing and never substitutes a value.

The committed baseline carries aggregates plus machine, OS, and architecture provenance. It does not carry the sample series.

The README embeds the generated chart. Refreshing the baseline after a change is a `make profile` run on the installed app.

## Alternatives rejected

- Publish RSS: it disagrees with Activity Monitor on the same idle process.
- Keep the historical HUD numbers: they do not describe the current build or idle.
- Measure from a Debug process or a fixture in place of the live app: those are not the installed artifact.
- Commit the sample series: aggregates plus provenance are enough to regenerate the chart.

## Consequences

The documented numbers are only as current as the last successful `make profile` on this machine class. Non-idle states, synthesized input, and CI gates stay out of scope.

A missing baseline fails the chart renderer rather than inventing a picture.

## Conditions for reconsideration

Revisit if a second measured state is added, if the OS reader changes, or if a CI performance gate is explicitly requested.

## Evidence

Issue #8 records the exact-path process rule, the physical-footprint label, the unpaired-sample rule, and the fail-closed chart contract.
