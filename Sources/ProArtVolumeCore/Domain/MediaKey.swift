package enum MediaKey: Equatable, Hashable, Sendable {
    case volumeUp
    case volumeDown
    case mute

    package var command: MediaKeyCommand {
        switch self {
        case .volumeUp:
            .step(.increase)
        case .volumeDown:
            .step(.decrease)
        case .mute:
            .toggleMute
        }
    }
}

package enum MediaKeyCommand: Equatable, Sendable {
    case step(VolumeStep)
    case toggleMute
}

package enum MediaKeyPhase: Equatable, Sendable {
    case down
    case up
}

package struct MediaKeyEvent: Equatable, Sendable {
    package let key: MediaKey
    package let phase: MediaKeyPhase

    package init(key: MediaKey, phase: MediaKeyPhase) {
        self.key = key
        self.phase = phase
    }
}

package enum MediaKeyRoutingDecision: Equatable, Sendable {
    case passThrough
    case consumeKeyDown(MediaKeyCommand)
    case consumeKeyUp
}

package struct MediaKeyRouting: Sendable {
    private var consumedKeyDowns: Set<MediaKey> = []

    package init() {}

    package mutating func decision(
        for event: MediaKeyEvent?,
        targetIsActive: Bool
    ) -> MediaKeyRoutingDecision {
        guard let event else {
            return .passThrough
        }
        switch event.phase {
        case .down:
            guard targetIsActive else {
                return .passThrough
            }
            consumedKeyDowns.insert(event.key)
            return .consumeKeyDown(event.key.command)
        case .up:
            let hasConsumedKeyDown = consumedKeyDowns.remove(event.key) != nil
            return targetIsActive && hasConsumedKeyDown ? .consumeKeyUp : .passThrough
        }
    }
}
