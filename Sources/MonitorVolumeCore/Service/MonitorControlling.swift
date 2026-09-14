package protocol MonitorControlling: MonitorStateReading {
    func writeVolume(_ volume: VolumeLevel, for target: MonitorIdentity) async throws(MonitorRepositoryError) -> VolumeLevel
    func writeMute(_ mute: MuteState, for target: MonitorIdentity) async throws(MonitorRepositoryError) -> MuteState
}
