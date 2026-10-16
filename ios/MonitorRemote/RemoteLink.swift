import MonitorRemoteProtocol

/// A connection to Monitor Volume on the Mac that discovers, connects, and
/// reconnects on its own, reporting each change as an observation.
@MainActor
protocol RemoteLink: AnyObject {
    func start(observing: @escaping @MainActor (RemoteLinkObservation) -> Void)
    func stop()
    func send(_ command: RemoteCommand)
}
