import Foundation
import MonitorRemoteProtocol
import MonitorVolumeCore
import Network
import OSLog

/// Advertises the remote service and turns validated commands from one
/// companion connection at a time into system media key events. The
/// connection is unauthenticated by decision (ADR 0007).
@MainActor
final class RemoteCommandListener {
    private static let firstRestartDelay = Duration.seconds(5)
    private static let longestRestartDelay = Duration.seconds(300)

    private let poster: SystemMediaKeyPoster
    private let logger = Logger(subsystem: "dev.taekwondodev.MonitorVolume", category: "remote")
    private var listener: NWListener?
    private var connection: (id: UInt64, connection: NWConnection)?
    private var ingress = RemoteIngressState()
    private var nextConnectionID: UInt64 = 0
    private var pendingRestart: Task<Void, Never>?
    /// Doubles after each failed start and resets once the listener is ready.
    private var restartDelay = firstRestartDelay

    init(poster: SystemMediaKeyPoster) {
        self.poster = poster
    }

    isolated deinit {
        stop()
    }

    /// Starts advertising unless already running.
    func start() {
        guard listener == nil else { return }
        pendingRestart?.cancel()
        pendingRestart = nil
        let listener: NWListener
        do {
            listener = try NWListener(using: .tcp)
        } catch {
            logger.error("listener creation failed: \(error, privacy: .public)")
            scheduleRestart()
            return
        }
        listener.service = NWListener.Service(type: RemoteService.type)
        listener.stateUpdateHandler = { [weak self, weak listener] state in
            MainActor.assumeIsolated {
                guard let self, let listener else { return }
                self.listener(listener, changedTo: state)
            }
        }
        listener.newConnectionHandler = { [weak self] connection in
            MainActor.assumeIsolated {
                self?.accept(connection)
            }
        }
        self.listener = listener
        listener.start(queue: .main)
    }

    /// Releases held remote keys, then stops advertising and drops the connection.
    func stop() {
        pendingRestart?.cancel()
        pendingRestart = nil
        endConnection()
        listener?.cancel()
        listener = nil
    }

    private func listener(_ listener: NWListener, changedTo state: NWListener.State) {
        guard self.listener === listener else { return }
        switch state {
        case let .failed(error):
            logger.error("listener failed: \(error, privacy: .public)")
            stop()
            scheduleRestart()
        case .ready:
            restartDelay = Self.firstRestartDelay
        case let .waiting(error):
            // Network.framework resumes a waiting listener once a usable network appears.
            logger.notice("listener waiting: \(error, privacy: .public)")
        case .setup, .cancelled:
            break
        @unknown default:
            break
        }
    }

    private func scheduleRestart() {
        let delay = restartDelay
        restartDelay = min(restartDelay * 2, Self.longestRestartDelay)
        pendingRestart = Task { [weak self] in
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled, let self else { return }
            self.pendingRestart = nil
            self.start()
        }
    }

    private func accept(_ newConnection: NWConnection) {
        nextConnectionID &+= 1
        let id = nextConnectionID
        let replaced = connection?.connection
        post(ingress.adopt(id))
        replaced?.stateUpdateHandler = nil
        replaced?.cancel()
        connection = (id, newConnection)
        newConnection.stateUpdateHandler = { [weak self] state in
            MainActor.assumeIsolated {
                switch state {
                case .failed, .cancelled:
                    self?.endConnection(id)
                case .setup, .preparing, .waiting, .ready:
                    break
                @unknown default:
                    break
                }
            }
        }
        newConnection.start(queue: .main)
        receive(on: newConnection, id: id)
    }

    private func receive(on connection: NWConnection, id: UInt64) {
        connection.receive(
            minimumIncompleteLength: 1,
            maximumLength: RemoteCommandCodec.maximumFrameBytes
        ) { [weak self] data, _, isComplete, error in
            MainActor.assumeIsolated {
                self?.received(data, isComplete: isComplete || error != nil, on: connection, id: id)
            }
        }
    }

    private func received(_ data: Data?, isComplete: Bool, on connection: NWConnection, id: UInt64) {
        guard self.connection?.id == id else { return }
        if let data, !data.isEmpty {
            let receipt = ingress.receive(data, on: id)
            post(receipt.events)
            if receipt.closesConnection {
                endConnection(id)
                return
            }
        }
        if isComplete {
            endConnection(id)
        } else {
            receive(on: connection, id: id)
        }
    }

    /// Ends the current connection, or only `id` when given, after releasing its held keys.
    private func endConnection(_ id: UInt64? = nil) {
        guard let current = connection, id == nil || current.id == id else { return }
        connection = nil
        post(ingress.close(current.id))
        current.connection.stateUpdateHandler = nil
        current.connection.cancel()
    }

    private func post(_ events: [MediaKeyEvent]) {
        for event in events {
            poster.post(event)
        }
    }
}
