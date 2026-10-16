import dnssd
import MonitorRemoteProtocol
import Network

/// Finds Monitor Volume through Bonjour and keeps one TCP connection to it,
/// rediscovering and reconnecting after failures and network changes.
@MainActor
final class NetworkRemoteLink: RemoteLink {
    private static let retryDelay = Duration.seconds(1)

    private var observer: (@MainActor (RemoteLinkObservation) -> Void)?
    private var observation = RemoteLinkObservation()
    private var pathMonitor: NWPathMonitor?
    private var browser: NWBrowser?
    private var connection: NWConnection?
    private var pendingRetry: Task<Void, Never>?

    func start(observing observer: @escaping @MainActor (RemoteLinkObservation) -> Void) {
        stop()
        self.observer = observer
        observation = RemoteLinkObservation()
        observer(observation)
        startPathMonitor()
        startBrowser()
    }

    func stop() {
        observer = nil
        pendingRetry?.cancel()
        pendingRetry = nil
        dropConnection()
        browser?.cancel()
        browser = nil
        pathMonitor?.cancel()
        pathMonitor = nil
    }

    func send(_ command: RemoteCommand) {
        guard observation.isConnected, let connection else { return }
        connection.send(content: RemoteCommandCodec.encode(command), completion: .idempotent)
    }

    private func update(_ change: (inout RemoteLinkObservation) -> Void) {
        var next = observation
        change(&next)
        guard next != observation else { return }
        observation = next
        observer?(next)
    }

    private func startPathMonitor() {
        let monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { [weak self] path in
            let isOnWiFi = path.status == .satisfied && path.usesInterfaceType(.wifi)
            MainActor.assumeIsolated {
                self?.pathChanged(isOnWiFi: isOnWiFi)
            }
        }
        pathMonitor = monitor
        monitor.start(queue: .main)
    }

    private func pathChanged(isOnWiFi: Bool) {
        let rejoinedWiFi = isOnWiFi && observation.isOnWiFi == false
        update { $0.isOnWiFi = isOnWiFi }
        if rejoinedWiFi {
            restartDiscovery()
        }
    }

    private func startBrowser() {
        let browser = NWBrowser(for: .bonjour(type: RemoteService.type, domain: nil), using: .tcp)
        browser.stateUpdateHandler = { [weak self, weak browser] state in
            MainActor.assumeIsolated {
                guard let self, let browser, self.browser === browser else { return }
                self.browserChanged(to: state)
            }
        }
        browser.browseResultsChangedHandler = { [weak self, weak browser] results, _ in
            MainActor.assumeIsolated {
                guard let self, let browser, self.browser === browser else { return }
                self.connectIfIdle(to: results)
            }
        }
        self.browser = browser
        browser.start(queue: .main)
    }

    private func browserChanged(to state: NWBrowser.State) {
        switch state {
        case .ready:
            update { $0.isLocalNetworkDenied = false }
        case let .waiting(error):
            update { $0.isLocalNetworkDenied = Self.isPolicyDenial(error) }
        case let .failed(error):
            update { $0.isLocalNetworkDenied = Self.isPolicyDenial(error) }
            scheduleRetry()
        case .setup, .cancelled:
            break
        @unknown default:
            break
        }
    }

    private func connectIfIdle(to results: Set<NWBrowser.Result>) {
        guard connection == nil, let endpoint = results.first?.endpoint else { return }
        let connection = NWConnection(to: endpoint, using: .tcp)
        connection.stateUpdateHandler = { [weak self, weak connection] state in
            MainActor.assumeIsolated {
                guard let self, let connection, self.connection === connection else { return }
                self.connectionChanged(connection, to: state)
            }
        }
        self.connection = connection
        connection.start(queue: .main)
    }

    private func connectionChanged(_ connection: NWConnection, to state: NWConnection.State) {
        switch state {
        case .ready:
            update {
                $0.isConnected = true
                $0.isLocalNetworkDenied = false
            }
            watchForClose(connection)
        case .waiting:
            let denied = connection.currentPath?.unsatisfiedReason == .localNetworkDenied
            update {
                $0.isConnected = false
                $0.isLocalNetworkDenied = denied
            }
            // A denied connection retries by itself once access is granted.
            if denied == false {
                connectionLost()
            }
        case .failed:
            connectionLost()
        case .setup, .preparing, .cancelled:
            break
        @unknown default:
            break
        }
    }

    /// The Mac never sends data, so a completed receive means it closed the connection.
    private func watchForClose(_ connection: NWConnection) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 1) { [weak self, weak connection] _, _, isComplete, error in
            MainActor.assumeIsolated {
                guard let self, let connection, self.connection === connection else { return }
                if isComplete || error != nil {
                    self.connectionLost()
                } else {
                    self.watchForClose(connection)
                }
            }
        }
    }

    private func connectionLost() {
        dropConnection()
        update { $0.isConnected = false }
        scheduleRetry()
    }

    private func dropConnection() {
        connection?.stateUpdateHandler = nil
        connection?.cancel()
        connection = nil
    }

    private func scheduleRetry() {
        guard pendingRetry == nil else { return }
        pendingRetry = Task { [weak self] in
            try? await Task.sleep(for: Self.retryDelay)
            guard Task.isCancelled == false, let self else { return }
            self.pendingRetry = nil
            self.restartDiscovery()
        }
    }

    private func restartDiscovery() {
        guard observer != nil else { return }
        dropConnection()
        update { $0.isConnected = false }
        browser?.cancel()
        startBrowser()
    }

    private static func isPolicyDenial(_ error: NWError) -> Bool {
        if case let .dns(code) = error {
            return code == DNSServiceErrorType(kDNSServiceErr_PolicyDenied)
        }
        return false
    }
}
