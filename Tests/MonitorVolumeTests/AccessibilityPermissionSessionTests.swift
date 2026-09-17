import CoreGraphics
import Foundation
import Testing
@testable import MonitorVolume

@MainActor
struct AccessibilityPermissionSessionTests {
    @Test
    func trustedSessionDoesNotPresentGuidance() {
        let rig = PermissionSessionRig(trusted: true)

        #expect(rig.session.beginGuided(for: 1) == .alreadyGranted)
        #expect(rig.settings.openCount == 0)
        #expect(rig.overlay.presentedApplicationURLs.isEmpty)
    }

    @Test
    func missingPermissionStartsOneGuidedSession() {
        let rig = PermissionSessionRig(trusted: false)

        #expect(rig.session.beginGuided(for: 7) == .waitingForGrant)
        #expect(rig.session.beginGuided(for: 7) == .waitingForGrant)
        #expect(rig.settings.openCount == 1)
        #expect(rig.overlay.presentedApplicationURLs == [rig.applicationURL])
    }

    @Test
    func silentWaitDoesNotPresentGuidance() {
        let rig = PermissionSessionRig(trusted: false)

        rig.session.beginSilent(for: 4)

        #expect(rig.settings.openCount == 0)
        #expect(rig.overlay.presentedApplicationURLs.isEmpty)
    }

    @Test
    func verifiedGrantCompletesCurrentGenerationExactlyOnce() {
        let rig = PermissionSessionRig(trusted: false)
        _ = rig.session.beginGuided(for: 9)
        rig.trust.isGranted = true

        rig.session.refreshGrant()
        rig.session.refreshGrant()

        #expect(rig.grantedGenerations == [9])
        #expect(rig.settings.closeCount == 1)
        #expect(rig.overlay.dismissCount == 1)
    }

    @Test
    func supersededGenerationCannotComplete() {
        let rig = PermissionSessionRig(trusted: false)
        _ = rig.session.beginGuided(for: 3)
        rig.session.beginSilent(for: 4)
        rig.trust.isGranted = true

        rig.session.refreshGrant()

        #expect(rig.grantedGenerations == [4])
    }

    @Test
    func sleepingSessionIgnoresLaterGrantAndCleanupIsIdempotent() {
        let rig = PermissionSessionRig(trusted: false)
        _ = rig.session.beginGuided(for: 2)

        rig.session.end(.sleep)
        rig.session.end(.sleep)
        rig.trust.isGranted = true
        rig.session.refreshGrant()

        #expect(rig.grantedGenerations.isEmpty)
        #expect(rig.overlay.dismissCount == 1)
        #expect(rig.settings.closeCount == 0)
    }
}

struct SystemSettingsWindowOwnershipTests {
    @Test
    func selectsTheOnlyWindowCreatedAfterTheBaseline() {
        let existing = settingsWindow(id: 1)
        let opened = settingsWindow(id: 2)
        var ownership = SystemSettingsWindowOwnership(baseline: [existing.identity])

        ownership.refresh(current: [existing, opened])

        #expect(ownership.ownedWindow == opened)
    }

    @Test
    func preservesPreexistingAndAmbiguousWindows() {
        let existing = settingsWindow(id: 1)
        let firstNew = settingsWindow(id: 2)
        let secondNew = settingsWindow(id: 3)
        var ownership = SystemSettingsWindowOwnership(baseline: [existing.identity])

        ownership.refresh(current: [existing])
        #expect(ownership.ownedWindow == nil)
        ownership.refresh(current: [existing, firstNew, secondNew])
        #expect(ownership.ownedWindow == nil)
        ownership.refresh(current: [existing, firstNew])
        #expect(ownership.ownedWindow == nil)
    }

    @Test
    func neverReassignsOwnershipAfterTheClaimedWindowDisappears() {
        let opened = settingsWindow(id: 2)
        let unrelated = settingsWindow(id: 3)
        var ownership = SystemSettingsWindowOwnership(baseline: [])

        ownership.refresh(current: [opened])
        ownership.refresh(current: [])
        ownership.refresh(current: [unrelated])

        #expect(ownership.ownedWindow == nil)
    }

    private func settingsWindow(id: CGWindowID) -> SystemSettingsWindowSnapshot {
        SystemSettingsWindowSnapshot(
            identity: SystemSettingsWindowIdentity(processID: 42, windowID: id),
            frame: CGRect(x: Int(id) * 10, y: 20, width: 800, height: 600)
        )
    }
}

@MainActor
private final class PermissionSessionRig {
    let applicationURL = URL(fileURLWithPath: "/Applications/Monitor Volume.app")
    let trust: FakeAccessibilityTrust
    let settings = FakeAccessibilitySettingsSession()
    let overlay = FakeAccessibilityPermissionOverlay()
    private(set) var grantedGenerations: [UInt64] = []
    lazy var session = AccessibilityPermissionSession(
        applicationURL: applicationURL,
        trust: trust,
        settings: settings,
        overlay: overlay
    ) { [weak self] generation in
        self?.grantedGenerations.append(generation)
    }

    init(trusted: Bool) {
        trust = FakeAccessibilityTrust(isGranted: trusted)
    }

    isolated deinit {
        session.end()
    }
}

@MainActor
private final class FakeAccessibilityTrust: AccessibilityTrustChecking {
    var isGranted: Bool

    init(isGranted: Bool) {
        self.isGranted = isGranted
    }
}

@MainActor
private final class FakeAccessibilitySettingsSession: AccessibilitySettingsSession {
    private(set) var openCount = 0
    private(set) var refreshCount = 0
    private(set) var closeCount = 0

    func openAccessibility() {
        openCount += 1
    }

    func refreshOwnership() {
        refreshCount += 1
    }

    func closeOwnedWindow() {
        closeCount += 1
    }

    func frontmostWindowFrame() -> CGRect? {
        nil
    }
}

@MainActor
private final class FakeAccessibilityPermissionOverlay: AccessibilityPermissionOverlay {
    private(set) var presentedApplicationURLs: [URL] = []
    private(set) var dismissCount = 0

    func present(applicationURL: URL) {
        presentedApplicationURLs.append(applicationURL)
    }

    func dismiss() {
        dismissCount += 1
    }
}
