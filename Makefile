.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: help test check build verify measure-latency latency-report offline-contract issue33-protocol issue33-doctor issue33-setup issue33-stop issue33-cleanup clean

help:
	@printf '%s\n' \
		'ProArt Volume commands:' \
		'  make test    Run the Swift test suite' \
		'  make check   Run the strict Release build and tooling checks' \
		'  make build   Build, sign, install, and launch the Release app' \
		'  make verify  Verify the installed bundle and exact live process' \
		'  make measure-latency  Install and arm Release latency capture' \
		'  make latency-report   Validate and summarize the latest capture' \
		'  make offline-contract Run one candidate-bound offline apparatus gate' \
		'  make issue33-protocol Validate and render the frozen installed A/B protocol' \
		'  make issue33-doctor Check pinned candidate worktrees without live actions' \
		'  make issue33-setup Install both candidates for manual Accessibility setup' \
		'  make issue33-stop Stop only the exact installed app process' \
		'  make issue33-cleanup Remove exact campaign candidates after manual TCC cleanup' \
		'  make clean   Remove only SwiftPM build artifacts'

test:
	@cd "$(ROOT)" && swift test

check:
	@"$(ROOT)scripts/check.sh"

build:
	@"$(ROOT)scripts/build-app.sh"

verify:
	@"$(ROOT)scripts/verify-installed-app.sh"

measure-latency:
	@"$(ROOT)scripts/measure-latency.sh"

latency-report:
	@"$(ROOT)scripts/latency-report.sh"

offline-contract:
	@"$(ROOT)scripts/offline-contract.sh"

issue33-protocol:
	@/usr/bin/python3 "$(ROOT)scripts/issue33_live_protocol.py"

issue33-doctor:
	@"$(ROOT)scripts/issue33-live.sh" doctor \
		--candidate-a-worktree "$${ISSUE33_A_WORKTREE:?Set ISSUE33_A_WORKTREE}" \
		--candidate-b-worktree "$${ISSUE33_B_WORKTREE:?Set ISSUE33_B_WORKTREE}"

issue33-stop:
	@"$(ROOT)scripts/issue33-live.sh" stop \
		--campaign-dir "$${ISSUE33_CAMPAIGN_DIR:?Set ISSUE33_CAMPAIGN_DIR}"

issue33-setup:
	@"$(ROOT)scripts/issue33-live.sh" setup \
		--campaign-dir "$${ISSUE33_CAMPAIGN_DIR:?Set ISSUE33_CAMPAIGN_DIR}" \
		--consent installationAndLaunch \
		--consent accessibilityPermissionChanges

issue33-cleanup:
	@"$(ROOT)scripts/issue33-live.sh" cleanup \
		--campaign-dir "$${ISSUE33_CAMPAIGN_DIR:?Set ISSUE33_CAMPAIGN_DIR}" \
		--accessibility-removal-recorded

clean:
	@cd "$(ROOT)" && swift package clean
