package protocol MonitorControlling: MonitorStateReading {
    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel
    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState
}
