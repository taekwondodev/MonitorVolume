# Proposed additions to repository Makefile. Existing command mappings stay unchanged.

.PHONY: ios-ipa ios-test ios-check

# Destination should be configured in CI to an available simulator runtime.
ios-test:
	xcodebuild test -project ios/MonitorRemote.xcodeproj -scheme MonitorRemote \
	  -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO

ios-check:
	xcodebuild build -project ios/MonitorRemote.xcodeproj -scheme MonitorRemote \
	  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO

ios-ipa:
	./scripts/build-ios-ipa.sh
