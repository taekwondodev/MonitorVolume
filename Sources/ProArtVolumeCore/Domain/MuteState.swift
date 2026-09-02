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
}
