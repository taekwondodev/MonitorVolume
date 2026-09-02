package struct ConfirmedMonitorState: Equatable, Sendable {
    package let volume: VolumeLevel
    package let mute: MuteState

    package init(volume: VolumeLevel, mute: MuteState) {
        self.volume = volume
        self.mute = mute
    }
}
