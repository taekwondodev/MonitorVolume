package enum MonitorRepositoryError: Error, Equatable, Sendable {
    case malformedResponse
    case readFailure
}
