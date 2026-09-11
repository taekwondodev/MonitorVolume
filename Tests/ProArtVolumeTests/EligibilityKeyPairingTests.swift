import Testing
@testable import ProArtVolumeCore

struct EligibilityKeyPairingTests {
    @Test
    func keyUpPairingSurvivesSuspensionUntilTapRelease() throws {
        let gate = try makeEligibleGate()
        _ = gate.route(keyDown(.volumeUp), at: 10)
        _ = gate.suspend(.tapDisabledByTimeout)

        #expect(gate.route(keyUp(.volumeUp), at: 20) == .consumeKeyUp)
        gate.releaseTap()
        #expect(gate.route(keyUp(.volumeDown), at: 30) == .passThrough)
    }

    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func keyUpPairingSurvivesEligibilityLoss(_ key: MediaKey) throws {
        let gate = try makeEligibleGate()
        _ = gate.route(keyDown(key), at: 10)
        _ = gate.invalidate()

        #expect(gate.route(keyUp(key), at: 20) == .consumeKeyUp)
    }

    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func activeKeyDownsConsumeAndMatchingKeyUpsRemainPaired(_ key: MediaKey) throws {
        let gate = try makeEligibleGate()

        guard case .consumeKeyDown = gate.route(keyDown(key), at: 10) else {
            Issue.record("active key-down must be admitted")
            return
        }
        #expect(gate.route(keyUp(key), at: 20) == .consumeKeyUp)
    }

    @Test
    func unmatchedKeyUpPassesThrough() throws {
        let gate = try makeEligibleGate()

        #expect(gate.route(keyUp(.volumeUp), at: 10) == .passThrough)
    }

    @Test
    func activeTapPassesNewInputThroughWhileHardwareIsUnavailable() throws {
        let gate = try makeEligibleGate()
        _ = gate.invalidate()

        #expect(gate.phase == .activeWithoutHardware)
        #expect(gate.route(keyDown(.volumeUp), at: 10) == .passThrough)
    }

    @Test
    func admittedPressesArriveInOrderAndFreeCapacityWhenDone() throws {
        let gate = try makeEligibleGate(capacity: 2)
        _ = gate.route(keyDown(.volumeUp), at: 10)
        _ = gate.route(keyDown(.volumeDown), at: 20)
        guard let first = gate.dequeue(), let second = gate.dequeue() else {
            Issue.record("expected two queued deliveries")
            return
        }
        #expect(first.sequence < second.sequence)
        #expect(first.command == .step(.increase))
        #expect(second.command == .step(.decrease))
        #expect(gate.complete(first))
        guard case let .consumeKeyDown(third) = gate.route(keyDown(.mute), at: 30) else {
            Issue.record("completion must release one admission slot")
            return
        }
        #expect(gate.pendingDeliveryCount == 2)
        #expect(gate.dequeue()?.sequence == third.sequence)
        #expect(gate.complete(second))
        #expect(gate.complete(third))
        #expect(gate.pendingDeliveryCount == 0)
    }
}
