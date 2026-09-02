package protocol ActiveAudioOutputReading: Sendable {
    func isTargetActive() async throws(MonitorRepositoryError) -> Bool
}
