// Design sketch only. The shared protocol target is Foundation-only and is consumed
// by both Xcode iOS app and existing macOS SwiftPM executable.

import Foundation

public enum RemoteKey: String, Codable, Sendable {
    case volumeUp
    case volumeDown
    case mute
}

public enum RemotePhase: String, Codable, Sendable {
    case down
    case up
}

/// Versioned operation transported as one newline-terminated UTF-8 JSON value.
public struct RemoteCommand: Codable, Equatable, Sendable {
    public static let currentVersion: UInt8 = 1
    public let version: UInt8
    public let key: RemoteKey
    public let phase: RemotePhase

    public init(key: RemoteKey, phase: RemotePhase) {
        self.version = Self.currentVersion
        self.key = key
        self.phase = phase
    }
}

public enum RemoteProtocolError: Error, Equatable {
    case malformedFrame
    case unsupportedVersion(UInt8)
    case frameTooLarge
}

public enum RemoteLineCodec {
    public static let maximumFrameBytes = 256

    public static func encode(_ command: RemoteCommand) throws -> Data {
        // not implemented: encode one JSON object and append LF
        throw NSError(domain: "not implemented", code: 1)
    }

    public static func decode(line: Data) throws -> RemoteCommand {
        // TODO require LF-terminated bounded frame; decode typed values; require currentVersion
        throw NSError(domain: "not implemented", code: 1)
    }
}

#if os(macOS)
import AppKit
import CoreGraphics
import Network
import MonitorVolumeCore

/// App-local adapter; no API is added to MonitorVolumeCore.
@MainActor final class SystemMediaKeyPoster {
    func post(_ command: RemoteCommand) {
        // TODO map RemoteKey/phase to exactly the parser's keycode/state and post NX_SYSDEFINED.
        // Ensure posting location/source is observed by the existing session event tap.
    }
}

@MainActor final class RemoteCommandListener {
    private let poster: SystemMediaKeyPoster
    private var listener: NWListener?
    private var connections: [UUID: RemoteConnection] = [:]

    init(poster: SystemMediaKeyPoster) { self.poster = poster }

    /// Idempotently starts advertising one versioned Bonjour service.
    func start() {
        // not implemented: create NWListener using TCP, install service metadata and state handler
    }

    /// Idempotently cancels listener/connections and posts up for each outstanding key.
    func stop() {
        // not implemented: release per-client held keys before canceling network objects
    }

    private func receive(_ connectionID: UUID, bytes: Data, complete: Bool) {
        // TODO append to only this connection's buffer; extract bounded LF frames;
        // reject malformed frames by closing this connection; translate down/repeat/up.
    }
}

/// Mutable state is actor-local to a single connection, never shared between clients.
private struct RemoteConnection {
    var buffer = Data()
    var heldKeys: Set<RemoteKey> = []
}
#endif

#if os(iOS)
import Network
import SwiftUI
import UIKit

@MainActor @Observable final class RemoteController {
    private(set) var status: RemoteStatus = .noMacFound
    private let browser = RemoteBrowser()
    private let connection = RemoteConnectionClient()

    func start() {
        // TODO begin NWBrowser for the versioned service, update status and connect
    }

    func press(_ key: RemoteKey) {
        guard status == .connected else { return }
        connection.send(RemoteCommand(key: key, phase: .down))
    }

    func repeatPress(_ key: RemoteKey) {
        guard status == .connected else { return }
        connection.send(RemoteCommand(key: key, phase: .down))
    }

    func release(_ key: RemoteKey) {
        guard status == .connected else { return }
        connection.send(RemoteCommand(key: key, phase: .up))
    }

    func openLocalNetworkSettings() {
        // not implemented: open this app's Settings page
    }
}

enum RemoteStatus: Equatable {
    case connected
    case noMacFound
    case notOnWiFi
    case localNetworkDenied

    var label: String {
        switch self {
        case .connected: "Connected"
        case .noMacFound: "No Mac found"
        case .notOnWiFi: "iPhone not on Wi-Fi"
        case .localNetworkDenied: "Local Network permission denied"
        }
    }
}

@MainActor final class RemoteBrowser {
    func start(onResult: @escaping (RemoteStatus, NWEndpoint?) -> Void) {
        // not implemented: NWBrowser; path monitoring; re-browse after path changes and wake
    }
    func stop() { /* not implemented */ }
}

@MainActor final class RemoteConnectionClient {
    func connect(to endpoint: NWEndpoint) { /* not implemented */ }
    func send(_ command: RemoteCommand) {
        // TODO encode via RemoteLineCodec and serialize NWConnection sends in order
    }
    func disconnect() { /* not implemented */ }
}

/// Gesture release must run on normal end and cancellation; repeat sends additional downs.
struct RemoteButtonsView: View {
    let controller: RemoteController

    var body: some View {
        VStack {
            Text(controller.status.label)
            button(.volumeUp)
            button(.volumeDown)
            button(.mute)
        }
    }

    private func button(_ key: RemoteKey) -> some View {
        Button(key.rawValue) { }
            .disabled(controller.status != .connected)
            // TODO use a press gesture with cancellable repeat task and guaranteed release;
            // trigger light UIKit haptic only on initial accepted send.
    }
}
#endif

// Existing coordinator integration, conceptual signature:
// @MainActor func attachRemoteIngress(_ listener: RemoteCommandListener)
// Launch starts ingress. Sleep and termination stop it. Wake restarts after
// successful event-tap open/revalidation. Keep lifecycle ownership in coordinator.
