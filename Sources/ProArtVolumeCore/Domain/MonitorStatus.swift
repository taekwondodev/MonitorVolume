package enum MonitorStatus: Equatable, Sendable {
    case confirmed(output: AudioOutputState, state: ConfirmedMonitorState)
    case commandFailure(
        output: AudioOutputState,
        state: ConfirmedMonitorState,
        error: MonitorRepositoryError
    )
    case unavailable
    case failure(MonitorRepositoryError)
}
