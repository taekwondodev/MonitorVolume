import Foundation
import MonitorRemoteProtocol
import MonitorVolumeCore

struct RemoteReceipt: Equatable {
    var events: [MediaKeyEvent] = []
    var closesConnection = false
}

/// Admits remote input from one connection at a time. Each connection has its
/// own frame buffer and held keys; leaving a connection releases its held keys.
struct RemoteIngressState {
    private var active: ActiveConnection?

    /// Makes `connection` the only connection. Returns the key-ups that release
    /// the replaced connection's held keys, which must be posted first.
    mutating func adopt(_ connection: UInt64) -> [MediaKeyEvent] {
        let released = releaseActive()
        active = ActiveConnection(id: connection)
        return released
    }

    mutating func receive(_ bytes: Data, on connection: UInt64) -> RemoteReceipt {
        guard var current = active, current.id == connection else {
            return RemoteReceipt(closesConnection: true)
        }
        var receipt = RemoteReceipt()
        do {
            for line in try current.framer.append(bytes) {
                let command = try RemoteCommandCodec.decode(line: line)
                if let event = current.admit(command) {
                    receipt.events.append(event)
                }
            }
            active = current
        } catch {
            active = current
            receipt.events += releaseActive()
            receipt.closesConnection = true
        }
        return receipt
    }

    /// Ends `connection` if it is still the active one and returns its releases.
    mutating func close(_ connection: UInt64) -> [MediaKeyEvent] {
        guard active?.id == connection else { return [] }
        return releaseActive()
    }

    mutating func closeAll() -> [MediaKeyEvent] {
        releaseActive()
    }

    private mutating func releaseActive() -> [MediaKeyEvent] {
        defer { active = nil }
        guard let active else { return [] }
        return RemoteKey.allCases
            .filter(active.heldKeys.contains)
            .map { MediaKeyEvent(key: MediaKey($0), phase: .up) }
    }
}

private struct ActiveConnection {
    let id: UInt64
    var framer = RemoteLineFramer()
    var heldKeys: Set<RemoteKey> = []

    mutating func admit(_ command: RemoteCommand) -> MediaKeyEvent? {
        switch command.phase {
        case .down:
            heldKeys.insert(command.key)
        case .up:
            guard heldKeys.remove(command.key) != nil else { return nil }
        }
        return MediaKeyEvent(key: MediaKey(command.key), phase: MediaKeyPhase(command.phase))
    }
}

extension MediaKey {
    init(_ key: RemoteKey) {
        self = switch key {
        case .volumeUp: .volumeUp
        case .volumeDown: .volumeDown
        case .mute: .mute
        }
    }
}

extension MediaKeyPhase {
    init(_ phase: RemotePhase) {
        self = switch phase {
        case .down: .down
        case .up: .up
        }
    }
}
