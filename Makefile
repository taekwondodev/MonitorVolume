.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: help test check build verify measure-latency latency-report clean

help:
	@printf '%s\n' \
		'ProArt Volume commands:' \
		'  make test    Run the Swift test suite' \
		'  make check   Run the strict Release build and tooling checks' \
		'  make build   Build, sign, install, and launch the Release app' \
		'  make verify  Verify the installed bundle and exact live process' \
		'  make measure-latency  Install and arm Release latency capture' \
		'  make latency-report   Validate and summarize the latest capture' \
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

clean:
	@cd "$(ROOT)" && swift package clean
