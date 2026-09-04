package enum MuteState: Equatable, Sendable {
    case muted
    case unmuted

    package init(hardwareValue: UInt16) throws(MonitorRepositoryError) {
        switch hardwareValue {
        case 1:
            self = .muted
        case 2:
            self = .unmuted
        default:
            throw .malformedResponse
        }
    }

    package var hardwareValue: UInt16 {
        switch self {
        case .muted:
            1
        case .unmuted:
            2
        }
    }

    package var toggled: MuteState {
        switch self {
        case .muted:
            .unmuted
        case .unmuted:
            .muted
        }
    }
}
