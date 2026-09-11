---
name: verify-proart-volume
description: Use when verifying ProArt Volume's invisible lifecycle, media-key OSD, and explicit hardware proof.
---

# Verify ProArt Volume

Verify the installed Release application through the repository-owned build and verification scripts. The helper owns only durable JSON evidence and the exact process launched by the build command.

## Doctor and ordinary verification

Run `make test` and `make check` before installation. Issue #32 candidate worktrees additionally use `make offline-contract` with explicit candidate, immutable source ref, and a fresh evidence directory; it runs one candidate gate and never performs A/B collection. Its comparative procedure is frozen separately in `scripts/issue32_collection_protocol.json`; validate or render it with `scripts/issue32_collection_protocol.py` without running either candidate. Use `make build` and `make verify` to install and check the real signed bundle and sole live process. Ordinary verification is non-invasive and does not prove hardware control, permission visibility, or OSD visuals.

Issue #33's installed comparison is separately frozen in `scripts/issue33_live_protocol.json`. Validate it with `make issue33-protocol` and check clean pinned candidates with `make issue33-doctor`. Neither command grants runtime consent. A separate `make issue33-setup` consent boundary installs the two manifest-bound candidate identities and waits for manual Accessibility grants plus per-candidate readiness. Before setup or any authorized run, keep `make issue33-stop` ready in a Terminal window and follow `references/features/live-comparison.md` exactly. During a measured run, the operator types every phase acknowledgement directly in that runner Terminal. Do not relay active-run prompts through chat or another mediated channel. Final `make issue33-cleanup` removes only the two verified campaign bundles after the operator records manual Accessibility-entry removal.

## Explicit hardware proof

Run from the repository root:

```sh
python3 .hermes/skills/verify-proart-volume/scripts/verify.py prove
```

A pass requires `status: passed`, a surviving evidence path, and no remaining owned process. The drive delegates build, bundle assembly, stable metadata, signing, installation, launch, process matching, and verification to `scripts/build-app.sh`, `scripts/verify-installed-app.sh`, and `scripts/stop-app.sh`.

## Evidence

Evidence lives under `.hermes/verification/evidence/<run-id>/launch.json`, with raw and validated hardware evidence in `hardware-*.json`. A pass requires bundle/process verification followed by actual volume/mute transitions and confirmed restorations. Nonzero probe results and malformed evidence remain failures and survive cleanup. See `references/features/hardware-proof.md` for the exact phase contract.

## Cleanup

`prove` calls `scripts/stop-app.sh` after a successful launch, including when later verification fails. Repository tooling revalidates the exact executable path before signalling a process. The installed bundle and evidence remain in place.

## Isolation

The installed bundle, PA279CV DDC channel, and macOS user session are shared resources. The proof stops the exact app before starting the hardware writer. Run serially with no external app launches, builds, direct probes, or other monitor-control tools. The tooling lock excludes concurrent proof wrappers, not arbitrary hardware writers. Explicit proof changes volume and mute briefly and attempts restoration. Never induce unconfirmed restoration on the physical monitor.

## Capability map

Read `references/features/README.md` before claiming coverage. The offline shared-contract drive is documented in `references/features/offline-comparison.md`; native permission/lifecycle scenarios and OSD visual acceptance remain live/manual obligations. Record each unexercised scenario rather than treating compilation, process liveness, synthetic traces, or a successful probe as a complete application proof.
