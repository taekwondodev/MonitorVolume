.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: help test check build verify profile ios-ipa clean

help:
	@printf '%s\n' \
		'Monitor Volume commands:' \
		'  make test     Run the Swift, protocol, and iOS simulator test suites' \
		'  make check    Run the strict Release builds for macOS and the iOS simulator, and tooling checks' \
		'  make build    Build, sign, install, and launch the Release app' \
		'  make verify   Verify the installed bundle and exact live process' \
		'  make profile  Measure idle CPU, physical footprint, and bundle size' \
		'  make ios-ipa  Build the unsigned Monitor Remote .ipa for SideStore' \
		'  make clean    Remove only SwiftPM build artifacts'

test:
	@cd "$(ROOT)" && swift test
	@cd "$(ROOT)" && swift test --package-path Shared/MonitorRemoteProtocol
	@"$(ROOT)scripts/ios.sh" test

check:
	@"$(ROOT)scripts/check.sh"
	@"$(ROOT)scripts/ios.sh" check

build:
	@"$(ROOT)scripts/build-app.sh"

verify:
	@"$(ROOT)scripts/verify-installed-app.sh"

profile:
	@"$(ROOT)scripts/profile-app.sh"

ios-ipa:
	@"$(ROOT)scripts/ios.sh" ipa

clean:
	@cd "$(ROOT)" && swift package clean
