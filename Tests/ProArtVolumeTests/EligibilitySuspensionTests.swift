import Testing
@testable import ProArtVolumeCore

struct EligibilitySuspensionTests {
    @Test(arguments: [
        InputSuspensionReason.missingPermission,
        .permissionRevoked,
        .tapDisabledByTimeout,
        .tapDisabledByUserInput,
        .tapCreationFailed,
        .deliveryOverflow,
    ])
    func suspensionRemainsLatchedUntilReopen(_ reason: InputSuspensionReason) throws {
        let gate = try makeEligibleGate()
        let oldSession = try #require(gate.session)
        let oldGeneration = gate.generation

        #expect(gate.allowsPermissionPolling)
        _ = gate.suspend(reason)

        #expect(gate.phase == .suspended(reason))
        #expect(gate.generation > oldGeneration)
        #expect(!gate.allowsPermissionPolling)
        #expect(gate.route(keyDown(.volumeUp), at: 10) == .passThrough)
        gate.publish(oldSession)
        #expect(gate.session == nil)
        gate.releaseTap()

        guard case let .started(newGeneration) = gate.reopen() else {
            Issue.record("reopen must start after no tap owner is active")
            return
        }
        #expect(newGeneration > oldSession.generation)
        #expect(gate.phase == .validating)
        let newSession = try ControlSession.fixture(
            generation: newGeneration,
            seedRevision: 2,
            volume: oldSession.seed.volume.rawValue,
            mute: oldSession.seed.mute
        )
        gate.publish(newSession)
        #expect(gate.contains(newSession))
        #expect(gate.allowsPermissionPolling)
    }

    @Test
    func repeatedSuspensionKeepsTheFirstReason() throws {
        let gate = try makeEligibleGate()

        let firstGeneration = gate.suspend(.permissionRevoked)
        let repeatedGeneration = gate.suspend(.deliveryOverflow)

        #expect(repeatedGeneration == firstGeneration)
        #expect(gate.phase == .suspended(.permissionRevoked))
    }

    @Test(arguments: [InputSuspensionReason.missingPermission, .permissionRevoked])
    func waitingForPermissionKeepsWatchingAndReopensOnceGranted(_ reason: InputSuspensionReason) throws {
        let gate = try makeEligibleGate()
        gate.releaseTap()
        _ = gate.suspend(reason)

        #expect(gate.awaitsPermission)
        #expect(!gate.allowsPermissionPolling)
        guard case .started = gate.reopen() else {
            Issue.record("granting permission must allow the suspended gate to reopen")
            return
        }
        #expect(gate.phase == .validating)
        #expect(!gate.awaitsPermission)
    }

    @Test(arguments: [
        InputSuspensionReason.tapDisabledByTimeout,
        .tapDisabledByUserInput,
        .tapCreationFailed,
        .deliveryOverflow,
    ])
    func systemSuspensionsDoNotWaitForPermission(_ reason: InputSuspensionReason) throws {
        let gate = try makeEligibleGate()
        _ = gate.suspend(reason)

        #expect(!gate.awaitsPermission)
    }

    @Test
    func passThroughAfterOverflowDiscardsHeldDeliveryAndPassesTheRejectedKey() throws {
        let gate = try makeEligibleGate(capacity: 2)
        let first = gate.route(keyDown(.volumeUp), at: 10)
        let second = gate.route(keyDown(.volumeDown), at: 20)

        guard case .consumeKeyDown = first, case .consumeKeyDown = second else {
            Issue.record("expected the configured capacity to be admitted")
            return
        }
        #expect(gate.pendingDeliveryCount == 2)
        #expect(gate.route(keyDown(.mute), at: 30) == .passThroughAfterOverflow)
        #expect(gate.phase == .suspended(.deliveryOverflow))
        #expect(gate.pendingDeliveryCount == 0)
        #expect(gate.snapshot.metrics == InputAdmissionMetrics(
            attemptedCount: 3,
            admittedCount: 2,
            rejectedCount: 1,
            discardedCount: 2,
            overflowCount: 1,
            completedCount: 0,
            peakOutstanding: 2,
            maximumDeliveryWaitNanoseconds: 0
        ))
        #expect(gate.route(keyDown(.volumeUp), at: 40) == .passThrough)
    }

    @Test
    func reopenWaitsForOldTapOwnerTeardown() throws {
        let gate = try makeEligibleGate()
        _ = gate.route(keyDown(.volumeUp), at: 10)
        let generation = gate.generation
        let session = try #require(gate.session)

        #expect(gate.reopen() == .waitingForTapRelease)
        #expect(gate.generation == generation)
        #expect(gate.phase == .eligible(session))

        gate.releaseTap()
        #expect(gate.pendingDeliveryCount == 0)
        guard case let .started(reopened) = gate.reopen() else {
            Issue.record("reopen must proceed after tap teardown completes")
            return
        }
        #expect(reopened > generation)
    }

    @Test
    func ownerClaimWithoutDeliveryStillBlocksReopen() throws {
        let gate = try makeEligibleGate()
        let generation = gate.generation

        #expect(gate.claimTapOwner(generation: generation))
        #expect(gate.snapshot.tapOwnerActive)
        #expect(gate.reopen() == .waitingForTapRelease)

        gate.releaseTap()
        #expect(gate.reopen() != .waitingForTapRelease)
    }

    @Test
    func staleDeliveryStillCompletesButNeverRestoresEligibility() throws {
        let gate = try makeEligibleGate()
        guard case let .consumeKeyDown(delivery) = gate.route(keyDown(.volumeUp), at: 10) else {
            Issue.record("expected an admitted delivery")
            return
        }
        _ = gate.dequeue()
        _ = gate.suspend(.permissionRevoked)

        #expect(!gate.contains(delivery.session))
        #expect(gate.complete(delivery))
        #expect(gate.snapshot.metrics.completedCount == 1)
    }

    @Test
    func releasedTapCannotAdmitUntilReopenAndOwnerClaim() throws {
        let gate = try makeEligibleGate()
        gate.releaseTap()

        #expect(gate.route(keyDown(.volumeUp), at: 10) == .passThrough)
        guard case let .started(generation) = gate.reopen() else {
            Issue.record("reopen must start after tap release")
            return
        }
        let session = try ControlSession.fixture(
            generation: generation,
            seedRevision: 2,
            volume: 50,
            mute: .unmuted
        )
        gate.publish(session)
        #expect(gate.claimTapOwner(generation: generation))
        #expect(gate.route(keyDown(.volumeUp), at: 20) != .passThrough)
    }
}
