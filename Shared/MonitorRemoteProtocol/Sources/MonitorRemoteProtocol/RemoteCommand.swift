public enum RemoteKey: String, CaseIterable, Hashable, Sendable {
    case volumeUp
    case volumeDown
    case mute
}

public enum RemotePhase: String, CaseIterable, Hashable, Sendable {
    case down
    case up
}

public struct RemoteCommand: Equatable, Hashable, Sendable {
    public let key: RemoteKey
    public let phase: RemotePhase

    public init(key: RemoteKey, phase: RemotePhase) {
        self.key = key
        self.phase = phase
    }
}

public enum RemoteService {
    /// Bonjour service type the Mac advertises and the companion browses.
    /// Both apps also list it in `NSBonjourServices`.
    public static let type = "_monitorvol-v1._tcp"
}
