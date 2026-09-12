package protocol ActiveAudioOutputReading: Sendable {
    func resolveTarget() async throws(MonitorRepositoryError) -> AudioDisplayTarget?
}
