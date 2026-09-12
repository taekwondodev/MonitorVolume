import Testing
@testable import ProArtVolumeCore

func makeEligibleGate(volume: Int = 50, mute: MonitorMuteState = .unmuted) throws -> ControlEligibility {
    let gate = ControlEligibility()
    guard case let .started(generation) = gate.reopen() else {
        Issue.record("eligible fixture could not reopen")
        return gate
    }
    let session = try ControlSession.fixture(
        generation: generation,
        seedRevision: 1,
        volume: volume,
        mute: mute
    )
    gate.publish(session)
    guard gate.claimTapOwner(generation: generation) else {
        Issue.record("eligible fixture could not claim its tap owner")
        return gate
    }
    return gate
}

func keyDown(_ key: MediaKey) -> MediaKeyEvent {
    MediaKeyEvent(key: key, phase: .down)
}

func keyUp(_ key: MediaKey) -> MediaKeyEvent {
    MediaKeyEvent(key: key, phase: .up)
}

extension ControlSession {
    static func fixture(
        generation: UInt64,
        seedRevision: UInt64,
        volume: Int,
        mute: MonitorMuteState
    ) throws -> ControlSession {
        let audioDisplay = AudioDisplayTarget.fixture(name: "ASUS PA279CV", productID: 10_088)
        return ControlSession(
            generation: generation,
            seedRevision: seedRevision,
            target: ResolvedMonitorTarget(audioDisplay: audioDisplay, capabilities: mute.capabilities),
            seed: .init(volume: try #require(VolumeLevel(volume)), mute: mute)
        )
    }
}

extension AudioDisplayTarget {
    static func fixture(name: String, productID: UInt32) -> Self {
        Self(
            identity: MonitorIdentity(manufacturer: "AUS", productID: productID, serial: nil),
            displayName: name
        )
    }
}

extension ConfirmedMonitorState {
    static func fixture(volume: Int, mute: MonitorMuteState) throws -> Self {
        Self(volume: try #require(VolumeLevel(volume)), mute: mute)
    }
}
