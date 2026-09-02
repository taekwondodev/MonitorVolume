.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: help test check build verify clean

help:
	@printf '%s\n' \
		'ProArt Volume commands:' \
		'  make test    Run the Swift test suite' \
		'  make check   Run the strict Release build and tooling checks' \
		'  make build   Build, sign, install, and launch the Release app' \
		'  make verify  Verify the installed bundle and exact live process' \
		'  make clean   Remove only SwiftPM build artifacts'

test:
	@cd "$(ROOT)" && swift test

check:
	@"$(ROOT)scripts/check.sh"

build:
	@"$(ROOT)scripts/build-app.sh"

verify:
	@"$(ROOT)scripts/verify-installed-app.sh"

clean:
	@cd "$(ROOT)" && swift package clean
