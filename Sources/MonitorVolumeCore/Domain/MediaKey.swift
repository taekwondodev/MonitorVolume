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
