import Testing
@testable import ProArtVolumeCore

struct MediaKeyRoutingTests {
    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func consumesHandledKeyDownWhenTargetIsActive(_ key: MediaKey) {
        var routing = MediaKeyRouting()

        #expect(routing.decision(for: .init(key: key, phase: .down), targetIsActive: true) == .consumeKeyDown(key.command))
    }

    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func consumesHandledKeyUpWhenTargetIsActive(_ key: MediaKey) {
        var routing = MediaKeyRouting()
        _ = routing.decision(for: .init(key: key, phase: .down), targetIsActive: true)

        #expect(routing.decision(for: .init(key: key, phase: .up), targetIsActive: true) == .consumeKeyUp)
    }

    @Test(arguments: [MediaKey.volumeUp, .volumeDown, .mute])
    func passesHandledKeysThroughWhenTargetIsInactive(_ key: MediaKey) {
        var routing = MediaKeyRouting()

        #expect(routing.decision(for: .init(key: key, phase: .down), targetIsActive: false) == .passThrough)
        #expect(routing.decision(for: .init(key: key, phase: .up), targetIsActive: false) == .passThrough)
    }

    @Test
    func passesUnrelatedSystemEventThrough() {
        var routing = MediaKeyRouting()

        #expect(routing.decision(for: nil, targetIsActive: true) == .passThrough)
    }

    @Test
    func passesUnmatchedKeyUpThrough() {
        var routing = MediaKeyRouting()

        #expect(routing.decision(for: .init(key: .volumeUp, phase: .up), targetIsActive: true) == .passThrough)
    }

    @Test
    func passesCorrespondingKeyUpWhenTargetBecameInactive() {
        var routing = MediaKeyRouting()
        _ = routing.decision(for: .init(key: .volumeUp, phase: .down), targetIsActive: true)

        #expect(routing.decision(for: .init(key: .volumeUp, phase: .up), targetIsActive: false) == .passThrough)
    }
}
