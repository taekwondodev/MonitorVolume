package enum MonitorStatus: Equatable, Sendable {
    case confirmed(output: AudioOutputState, state: ConfirmedMonitorState)

    case unavailable
    case failure(MonitorRepositoryError)
}
