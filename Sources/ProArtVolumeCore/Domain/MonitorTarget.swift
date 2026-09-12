package struct AudioDisplayTarget: Equatable, Hashable, Sendable {
    package let identity: MonitorIdentity
    package let displayName: String

    package init(identity: MonitorIdentity, displayName: String) {
        self.identity = identity
        self.displayName = displayName
    }
}

package struct MonitorCapabilities: OptionSet, Equatable, Hashable, Sendable {
    package let rawValue: UInt8

    package init(rawValue: UInt8) {
        self.rawValue = rawValue
    }

    package static let volume = Self(rawValue: 1 << 0)
    package static let mute = Self(rawValue: 1 << 1)

    package func supports(_ command: MediaKeyCommand) -> Bool {
        switch command {
        case .step:
            contains(.volume)
        case .toggleMute:
            contains(.mute)
        }
    }
}

package struct ResolvedMonitorTarget: Equatable, Hashable, Sendable {
    package let audioDisplay: AudioDisplayTarget
    package let capabilities: MonitorCapabilities

    package init(audioDisplay: AudioDisplayTarget, capabilities: MonitorCapabilities) {
        self.audioDisplay = audioDisplay
        self.capabilities = capabilities
    }

    package var identity: MonitorIdentity { audioDisplay.identity }
    package var displayName: String { audioDisplay.displayName }
}
