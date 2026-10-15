// Shared target MonitorRemoteProtocol contains only these value shapes and codec.

public enum RemoteMessage: Equatable, Sendable {
    case command(RemoteCommand, RemotePhase)
}

public enum RemoteCommand: String, Codable, Sendable {
    case volumeUp
    case volumeDown
    case mute
}

public enum RemotePhase: String, Codable, Sendable {
    case down
    case up
}

public enum RemoteMessageCodec {
    /// Validate version and message shape at network boundary; wire framing is length-prefixed JSON.
    public static func decode(_ data: Data) throws -> RemoteMessage {
        fatalError("not implemented")
    }

    public static func encode(_ message: RemoteMessage) throws -> Data {
        fatalError("not implemented")
    }
}

// iOS target: no shared mutable state with Mac ingress.
@MainActor
final class RemoteClient: ObservableObject {
    enum Status: Equatable {
        case connected
        case noMacFound
        case notOnWiFi
        case localNetworkPermissionDenied
    }

    @Published private(set) var status: Status = .noMacFound
    private var held: Set<RemoteCommand> = []

    /// Owns NWBrowser/NWConnection, reconnection on path/failure, and typed status transitions.
    func start() { fatalError("not implemented") }
    func stop() { fatalError("not implemented") }

    /// Send down once, then repeated downs; each logical command release sends up.
    func press(_ command: RemoteCommand) async { fatalError("not implemented") }
    func repeatPress(_ command: RemoteCommand) async { fatalError("not implemented") }
    func release(_ command: RemoteCommand) async { fatalError("not implemented") }

    /// Scene background/disconnect sends up for every held command, then clears local held set.
    private func releaseAll() async { fatalError("not implemented") }
}

// SwiftUI view call sites:
// Button { Task { await model.press(.volumeUp); haptics.light() } } label: { Image(systemName: "speaker.plus") }
// .onLongPressGesture(minimumDuration: 0, pressing: { down in Task { down ? await model.repeatPress(.volumeUp) : await model.release(.volumeUp) } }, perform: {})
// .disabled(model.status != .connected)
// Persistent label switches over model.status; Settings link is shown only for permissionDenied.
