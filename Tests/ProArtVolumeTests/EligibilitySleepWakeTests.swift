import Testing
@testable import ProArtVolumeCore

struct EligibilitySleepWakeTests {
    @Test
    func activeWakeRequiresFreshValidationAndSuspendedWakeDoesNotReopen() throws {
        let gate = try makeEligibleGate()
        let oldSession = try #require(gate.session)
        let activeGeneration = gate.generation
        gate.releaseTap()
        let sleepingGeneration = gate.sleep()
        #expect(sleepingGeneration > activeGeneration)
        #expect(gate.sleep() > sleepingGeneration)
        #expect(gate.phase == .sleepingAfterActive)
        #expect(!gate.allowsPermissionPolling)
        guard case let .revalidate(wakeGeneration) = gate.wake() else {
            Issue.record("active wake must request validation")
            return
        }
        #expect(wakeGeneration > sleepingGeneration)
        #expect(gate.phase == .validating)
        #expect(gate.allowsPermissionPolling)
        let refreshed = try ControlSession.fixture(
            generation: wakeGeneration,
            seedRevision: 2,
            volume: oldSession.seed.volume.rawValue,
            mute: oldSession.seed.mute
        )
        gate.publish(refreshed)
        #expect(gate.contains(refreshed))

        _ = gate.suspend(.tapCreationFailed)
        let suspendedSleepGeneration = gate.sleep()
        #expect(gate.sleep() > suspendedSleepGeneration)
        #expect(gate.phase == .sleepingWhileSuspended(.tapCreationFailed))
        #expect(gate.wake() == .remainsSuspended(.tapCreationFailed))
        #expect(gate.phase == .suspended(.tapCreationFailed))
        #expect(gate.session == nil)
        #expect(!gate.allowsPermissionPolling)
    }

    @Test
    func wakeWaitsForTapReleaseWithoutBlocking() throws {
        let gate = try makeEligibleGate()
        _ = gate.route(keyDown(.volumeUp))
        _ = gate.sleep()

        #expect(gate.wake() == .waitingForTapRelease)
        gate.releaseTap()
        guard case .revalidate = gate.wake() else {
            Issue.record("wake must revalidate after tap teardown completes")
            return
        }
    }

    @Test
    func invalidatingActiveOwnerKeepsPermissionPollingLifecycleActive() throws {
        let gate = try makeEligibleGate()

        _ = gate.invalidate()

        #expect(gate.phase == .activeWithoutHardware)
        #expect(gate.session == nil)
        #expect(gate.allowsPermissionPolling)
        #expect(gate.snapshot.tapOwnerActive)
    }

    @Test
    func wakeFromUnavailableLifecycleDoesNotClaimHardwareEligibility() {
        let gate = ControlEligibility()
        let sleepingGeneration = gate.sleep()

        #expect(gate.phase == .sleepingWhileUnavailable)
        guard case let .remainsUnavailable(wakeGeneration) = gate.wake() else {
            Issue.record("unavailable wake must remain outside eligible state")
            return
        }
        #expect(wakeGeneration > sleepingGeneration)
        #expect(gate.phase == .unavailable)
        #expect(gate.session == nil)
        #expect(!gate.allowsPermissionPolling)
    }

    @Test
    func markingUnavailableDoesNotActivateUnavailableGate() {
        let gate = ControlEligibility()

        gate.markUnavailable(generation: gate.generation)

        #expect(gate.phase == .unavailable)
        #expect(!gate.allowsPermissionPolling)
    }
}
