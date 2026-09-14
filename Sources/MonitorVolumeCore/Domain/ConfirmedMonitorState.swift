package enum MonitorMuteState: Equatable, Sendable {
    case supported(MuteState)
    case unsupported

    package static let muted = Self.supported(.muted)
    package static let unmuted = Self.supported(.unmuted)

    package var capabilities: MonitorCapabilities {
        self == .unsupported ? [.volume] : [.volume, .mute]
    }

    package func applying(_ command: MediaKeyCommand) -> Self {
        switch (self, command) {
        case (.supported, .step):
            .supported(.unmuted)
        case let (.supported(mute), .toggleMute):
            .supported(mute.toggled)
        case (.unsupported, _):
            .unsupported
        }
    }
}

package struct ConfirmedMonitorState: Equatable, Sendable {
    package let volume: VolumeLevel
    package let mute: MonitorMuteState

    package init(volume: VolumeLevel, mute: MonitorMuteState) {
        self.volume = volume
        self.mute = mute
    }
}
