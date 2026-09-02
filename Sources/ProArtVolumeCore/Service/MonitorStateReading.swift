package protocol MonitorStateReading: Sendable {
    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState?
}
