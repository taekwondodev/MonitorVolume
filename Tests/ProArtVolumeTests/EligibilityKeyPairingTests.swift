import Testing
@testable import ProArtVolumeCore

struct EligibilityKeyPairingTests {
    @Test
    func volumeOnlySessionConsumesVolumeAndPassesBothMutePhasesThrough() throws {
        let gate = try makeEligibleGate(mute: .unsupported)

        guard case .consumeKeyDown = gate.route(keyDown(.volumeDown)) else {
            Issue.record("volume-down must be admitted for a volume-only session")
            return
        }
        #expect(gate.route(keyUp(.volumeDown)) == .consumeKeyUp)
        #expect(gate.route(keyDown(.mute)) == .passThrough)
        #expect(gate.route(keyUp(.mute)) == .passThrough)
    }

    @Test
    func keyUpPairingSurvivesSuspensionUntilTapRelease() throws {
        let gate = try makeEligibleGate()
        _ = gate.route(keyDown(.volumeUp))
        _ = gate.suspend(.tapDisabledByTimeout)

        #expect(gate.route(keyUp(.volumeUp)) == .consumeKeyUp)
        gate.releaseTap()
        #expect(gate.route(keyUp(.volumeDown)) == .passThrough)
    }

    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func keyUpPairingSurvivesEligibilityLoss(_ key: MediaKey) throws {
        let gate = try makeEligibleGate()
        _ = gate.route(keyDown(key))
        _ = gate.invalidate()

        #expect(gate.route(keyUp(key)) == .consumeKeyUp)
    }

    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func activeKeyDownsConsumeAndMatchingKeyUpsRemainPaired(_ key: MediaKey) throws {
        let gate = try makeEligibleGate()

        guard case .consumeKeyDown = gate.route(keyDown(key)) else {
            Issue.record("active key-down must be admitted")
            return
        }
        #expect(gate.route(keyUp(key)) == .consumeKeyUp)
    }

    @Test
    func unmatchedKeyUpPassesThrough() throws {
        let gate = try makeEligibleGate()

        #expect(gate.route(keyUp(.volumeUp)) == .passThrough)
    }

    @Test
    func activeTapPassesNewInputThroughWhileHardwareIsUnavailable() throws {
        let gate = try makeEligibleGate()
        _ = gate.invalidate()

        #expect(gate.phase == .activeWithoutHardware)
        #expect(gate.route(keyDown(.volumeUp)) == .passThrough)
    }

    @Test
    func admittedPressesArriveInOrder() throws {
        let gate = try makeEligibleGate()
        _ = gate.route(keyDown(.volumeUp))
        _ = gate.route(keyDown(.volumeDown))
        _ = gate.route(keyDown(.mute))
        #expect(gate.pendingDeliveryCount == 3)
        #expect(gate.dequeue()?.command == .step(.increase))
        #expect(gate.dequeue()?.command == .step(.decrease))
        #expect(gate.dequeue()?.command == .toggleMute)
        #expect(gate.dequeue() == nil)
        #expect(gate.pendingDeliveryCount == 0)
    }
}
