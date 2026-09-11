import Testing
@testable import ProArtVolumeCore

func makeEligibleGate(capacity: Int = 8, volume: Int = 50) throws -> ControlEligibility {
    let gate = ControlEligibility(capacity: capacity)
    guard case let .started(generation) = gate.reopen() else {
        Issue.record("eligible fixture could not reopen")
        return gate
    }
    let session = try ControlSession.fixture(
        generation: generation,
        seedRevision: 1,
        volume: volume,
        mute: .unmuted
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
        mute: MuteState
    ) throws -> ControlSession {
        ControlSession(
            generation: generation,
            seedRevision: seedRevision,
            seed: .init(volume: try #require(VolumeLevel(volume)), mute: mute)
        )
    }
}
