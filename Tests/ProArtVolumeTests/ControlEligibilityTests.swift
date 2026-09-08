import Testing
@testable import ProArtVolumeCore

struct ControlEligibilityTests {
    @Test(arguments: [
        InputSuspensionReason.missingPermission,
        .permissionRevoked,
        .tapDisabledByTimeout,
        .tapDisabledByUserInput,
        .tapCreationFailed,
        .deliveryOverflow,
    ])
    func suspensionRemainsLatchedUntilReopen(_ reason: InputSuspensionReason) throws {
        let gate = try eligibleGate()
        let oldSession = try #require(gate.session)
        let oldGeneration = gate.generation

        #expect(gate.allowsPermissionPolling)
        _ = gate.suspend(reason)

        #expect(gate.phase == .suspended(reason))
        #expect(gate.generation > oldGeneration)
        #expect(!gate.allowsPermissionPolling)
        #expect(gate.route(.init(key: .volumeUp, phase: .down), at: 10) == .passThrough)
        gate.publish(oldSession)
        #expect(gate.session == nil)
        gate.releaseTap()

        guard case let .started(newGeneration) = gate.reopen() else {
            Issue.record("reopen must start after no tap owner is active")
            return
        }
        #expect(newGeneration > oldSession.generation)
        #expect(gate.phase == .validating)
        let newSession = ControlSession(
            generation: newGeneration,
            seedRevision: 2,
            seed: oldSession.seed
        )
        gate.publish(newSession)
        #expect(gate.contains(newSession))
        #expect(gate.allowsPermissionPolling)
    }

    @Test
    func repeatedSuspensionDoesNotReplaceTheLatchedGenerationOrReason() throws {
        let gate = try eligibleGate()

        let firstGeneration = gate.suspend(.permissionRevoked)
        let repeatedGeneration = gate.suspend(.deliveryOverflow)

        #expect(repeatedGeneration == firstGeneration)
        #expect(gate.phase == .suspended(.permissionRevoked))
    }

    @Test
    func passThroughAfterOverflowDiscardsHeldDeliveryAndPassesTheRejectedKey() throws {
        let gate = try eligibleGate(capacity: 2)
        let first = gate.route(.init(key: .volumeUp, phase: .down), at: 10)
        let second = gate.route(.init(key: .volumeDown, phase: .down), at: 20)

        guard case .consumeKeyDown = first, case .consumeKeyDown = second else {
            Issue.record("expected the configured capacity to be admitted")
            return
        }
        #expect(gate.pendingDeliveryCount == 2)
        #expect(gate.route(.init(key: .mute, phase: .down), at: 30) == .passThroughAfterOverflow)
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
        #expect(gate.route(.init(key: .volumeUp, phase: .down), at: 40) == .passThrough)
    }

    @Test
    func keyUpPairingSurvivesSuspensionUntilTapRelease() throws {
        let gate = try eligibleGate()
        _ = gate.route(.init(key: .volumeUp, phase: .down), at: 10)
        _ = gate.suspend(.tapDisabledByTimeout)

        #expect(gate.route(.init(key: .volumeUp, phase: .up), at: 20) == .consumeKeyUp)
        gate.releaseTap()
        #expect(gate.route(.init(key: .volumeDown, phase: .up), at: 30) == .passThrough)
    }

    @Test
    func reopenWaitsForOldTapOwnerTeardown() throws {
        let gate = try eligibleGate()
        _ = gate.route(.init(key: .volumeUp, phase: .down), at: 10)
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
        let gate = try eligibleGate()
        let generation = gate.generation

        #expect(gate.claimTapOwner(generation: generation))
        #expect(gate.snapshot.tapOwnerActive)
        #expect(gate.reopen() == .waitingForTapRelease)

        gate.releaseTap()
        #expect(gate.reopen() != .waitingForTapRelease)
    }

    @Test
    func staleDeliveryCanCompleteBookkeepingButCannotRemainEligible() throws {
        let gate = try eligibleGate()
        guard case let .consumeKeyDown(delivery) = gate.route(
            .init(key: .volumeUp, phase: .down), at: 10
        ) else {
            Issue.record("expected an admitted delivery")
            return
        }
        _ = gate.dequeue()
        _ = gate.suspend(.permissionRevoked)

        #expect(!gate.contains(delivery.session))
        #expect(gate.complete(delivery))
        #expect(gate.snapshot.metrics.completedCount == 1)
    }

    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func activeKeyDownsConsumeAndMatchingKeyUpsRemainPaired(_ key: MediaKey) throws {
        let gate = try eligibleGate()

        guard case .consumeKeyDown = gate.route(.init(key: key, phase: .down), at: 10) else {
            Issue.record("active key-down must be admitted")
            return
        }
        #expect(gate.route(.init(key: key, phase: .up), at: 20) == .consumeKeyUp)
    }

    @Test
    func unmatchedKeyUpPassesThrough() throws {
        let gate = try eligibleGate()

        #expect(gate.route(.init(key: .volumeUp, phase: .up), at: 10) == .passThrough)
    }

    @Test
    func activeTapPassesNewInputThroughWhileHardwareIsUnavailable() throws {
        let gate = try eligibleGate()
        _ = gate.invalidate()

        #expect(gate.phase == .activeWithoutHardware)
        #expect(gate.route(.init(key: .volumeUp, phase: .down), at: 10) == .passThrough)
    }

    @Test
    func activeWakeRequiresFreshValidationAndSuspendedWakeDoesNotReopen() throws {
        let gate = try eligibleGate()
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
        let refreshed = ControlSession(generation: wakeGeneration, seedRevision: 2, seed: oldSession.seed)
        gate.publish(refreshed)
        #expect(gate.contains(refreshed))

        _ = gate.suspend(.deliveryOverflow)
        let suspendedSleepGeneration = gate.sleep()
        #expect(gate.sleep() > suspendedSleepGeneration)
        #expect(gate.phase == .sleepingWhileSuspended(.deliveryOverflow))
        #expect(gate.wake() == .remainsSuspended(.deliveryOverflow))
        #expect(gate.phase == .suspended(.deliveryOverflow))
        #expect(gate.session == nil)
        #expect(!gate.allowsPermissionPolling)
    }

    @Test
    func wakeWaitsForTapReleaseWithoutBlocking() throws {
        let gate = try eligibleGate()
        _ = gate.route(.init(key: .volumeUp, phase: .down), at: 10)
        _ = gate.sleep()

        #expect(gate.wake() == .waitingForTapRelease)
        gate.releaseTap()
        guard case .revalidate = gate.wake() else {
            Issue.record("wake must revalidate after tap teardown completes")
            return
        }
    }

    @Test
    func releasedTapCannotAdmitUntilReopenAndOwnerClaim() throws {
        let gate = try eligibleGate()
        gate.releaseTap()

        #expect(gate.route(.init(key: .volumeUp, phase: .down), at: 10) == .passThrough)
        guard case let .started(generation) = gate.reopen() else {
            Issue.record("reopen must start after tap release")
            return
        }
        let session = ControlSession(
            generation: generation,
            seedRevision: 2,
            seed: .init(volume: try #require(VolumeLevel(50)), mute: .unmuted)
        )
        gate.publish(session)
        #expect(gate.claimTapOwner(generation: generation))
        #expect(gate.route(.init(key: .volumeUp, phase: .down), at: 20) != .passThrough)
    }

    @Test
    func invalidatingActiveOwnerKeepsPermissionPollingLifecycleActive() throws {
        let gate = try eligibleGate()

        _ = gate.invalidate()

        #expect(gate.phase == .activeWithoutHardware)
        #expect(gate.session == nil)
        #expect(gate.allowsPermissionPolling)
        #expect(gate.snapshot.tapOwnerActive)
    }

    @Test
    func dequeuePreservesAdmissionOrderAndCapacityIsReleasedOnCompletion() throws {
        let gate = try eligibleGate(capacity: 2)
        _ = gate.route(.init(key: .volumeUp, phase: .down), at: 10)
        _ = gate.route(.init(key: .volumeDown, phase: .down), at: 20)
        guard let first = gate.dequeue(), let second = gate.dequeue() else {
            Issue.record("expected two queued deliveries")
            return
        }
        #expect(first.sequence < second.sequence)
        #expect(first.command == .step(.increase))
        #expect(second.command == .step(.decrease))
        #expect(gate.complete(first))
        guard case let .consumeKeyDown(third) = gate.route(.init(key: .mute, phase: .down), at: 30) else {
            Issue.record("completion must release one admission slot")
            return
        }
        #expect(gate.pendingDeliveryCount == 2)
        #expect(gate.dequeue()?.sequence == third.sequence)
        #expect(gate.complete(second))
        #expect(gate.complete(third))
        #expect(gate.pendingDeliveryCount == 0)
    }

    @Test
    func wakeFromUnavailableLifecycleDoesNotClaimHardwareEligibility() {
        let gate = ControlEligibility(capacity: 2)
        let sleepingGeneration = gate.sleep()

        #expect(gate.phase == .sleepingWhileUnavailable)
        guard case let .remainsUnavailable(wakeGeneration) = gate.wake() else {
            Issue.record("unavailable wake must remain outside eligible state")
            return
        }
        #expect(wakeGeneration > sleepingGeneration)
        #expect(gate.phase == .activeWithoutHardware)
        #expect(gate.session == nil)
        #expect(gate.allowsPermissionPolling)
    }

    @Test
    func markingUnavailableDoesNotActivateUnavailableGate() {
        let gate = ControlEligibility()

        gate.markUnavailable(generation: gate.generation)

        #expect(gate.phase == .unavailable)
        #expect(!gate.allowsPermissionPolling)
    }

    private func eligibleGate(capacity: Int = 8) throws -> ControlEligibility {
        let gate = ControlEligibility(capacity: capacity)
        guard case let .started(generation) = gate.reopen() else {
            Issue.record("eligible fixture could not reopen")
            return gate
        }
        let session = ControlSession(
            generation: generation,
            seedRevision: 1,
            seed: .init(volume: try #require(VolumeLevel(50)), mute: .unmuted)
        )
        gate.publish(session)
        guard gate.claimTapOwner(generation: generation) else {
            Issue.record("eligible fixture could not claim its tap owner")
            return gate
        }
        return gate
    }
}
