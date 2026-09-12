package protocol MonitorStateReading: Sendable {
    func readState(for target: MonitorIdentity) async throws(MonitorRepositoryError) -> ConfirmedMonitorState?
}
