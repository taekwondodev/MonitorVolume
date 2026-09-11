import Testing
@testable import ProArtVolumeCore

struct VolumeIntentTests {
    @Test(arguments: [(98, [100, 95]), (2, [0, 5])])
    func saturatesEachPressBeforeCoalescing(start: Int, expected: [Int]) throws {
        let session = try ControlSession.fixture(generation: 1, seedRevision: 1, volume: start, mute: .unmuted)
        var reducer = VolumeIntentReducer()
        let commands: [MediaKeyCommand] = start == 98
            ? [.step(.increase), .step(.decrease)] : [.step(.decrease), .step(.increase)]
        let values = commands.map { reducer.accept($0, session: session).intent.volume.rawValue }
        #expect(values == expected)
    }

    @Test func rapidPressesRetainIndividualIntents() throws {
        let session = try ControlSession.fixture(generation: 1, seedRevision: 1, volume: 50, mute: .unmuted)
        var reducer = VolumeIntentReducer()
        let values = (0..<3).map { _ in reducer.accept(.step(.increase), session: session).intent.volume.rawValue }
        #expect(values == [55, 60, 65])
    }

    @Test(arguments: [0, 100])
    func boundaryVolumeStillUnmutes(value: Int) throws {
        let initial = VolumeIntent(volume: try #require(VolumeLevel(value)), mute: .muted)
        let next = initial.applying(.step(value == 0 ? .decrease : .increase))
        #expect(next.volume.rawValue == value)
        #expect(next.mute == .unmuted)
    }

    @Test func togglesPreserveParity() throws {
        let initial = VolumeIntent(volume: try #require(VolumeLevel(50)), mute: .unmuted)
        let twice = initial.applying(.toggleMute).applying(.toggleMute)
        #expect(twice == initial)
        #expect(twice.applying(.toggleMute).mute == .muted)
    }

    @Test func recoveryReseedsInsteadOfReplayingDisplayedIntent() throws {
        var reducer = VolumeIntentReducer()
        let first = try ControlSession.fixture(generation: 1, seedRevision: 1, volume: 50, mute: .unmuted)
        _ = reducer.accept(.step(.increase), session: first)
        let recovered = try ControlSession.fixture(generation: 1, seedRevision: 2, volume: 80, mute: .muted)
        let next = reducer.accept(.step(.increase), session: recovered)
        #expect(next.intent.volume.rawValue == 85)
        #expect(next.intent.mute == .unmuted)
    }
}