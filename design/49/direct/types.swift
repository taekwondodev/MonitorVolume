// Candidate sketch. Existing Core domain types are package-scoped in MonitorVolumeCore.

package struct RemoteInputID: Hashable, Sendable {
    // Created once per accepted TCP connection; never derived from peer address.
    package let rawValue: UUID

    package init(rawValue: UUID) { self.rawValue = rawValue }
}

package enum InputSource: Hashable, Sendable {
    case physical
    case remote(RemoteInputID)
}

package struct AdmittedMediaKey: Equatable, Sendable {
    package let sequence: UInt64
    package let command: MediaKeyCommand
    package let session: ControlSession
    package let source: InputSource
}

package enum InputAdmissionDecision: Equatable, Sendable {
    case passThrough
    case consumeKeyDown(AdmittedMediaKey)
    case consumeKeyUp
}

package enum RemoteAdmissionResult: Equatable, Sendable {
    case admitted(AdmittedMediaKey)
    case notAdmitted
}

package final class ControlEligibility: Sendable {
    // Existing state additionally owns remoteConsumedKeyDowns:
    // [RemoteInputID: Set<MediaKey>]. Physical consumed keys remain separate.

    /// OS tap adapter: passThrough means return the original CGEvent unchanged.
    package func route(_ event: MediaKeyEvent) -> InputAdmissionDecision {
        fatalError("not implemented")
    }

    /// Network adapter: notAdmitted means no Monitor Volume action; never synthesize an OS event.
    package func admitRemote(
        _ key: MediaKey,
        phase: MediaKeyPhase,
        from input: RemoteInputID
    ) -> RemoteAdmissionResult {
        fatalError("not implemented")
    }

    /// Drop held-key pairing for one disconnected remote connection only.
    package func removeRemoteInput(_ input: RemoteInputID) {
        fatalError("not implemented")
    }

    /// Both admission methods append accepted downs to the one FIFO drained by existing dequeue().
    package func dequeue() -> AdmittedMediaKey? { fatalError("not implemented") }
}

@MainActor
final class RemoteCommandListener {
    private let eligibility: ControlEligibility
    private let coordinator: ApplicationCoordinator

    init(eligibility: ControlEligibility, coordinator: ApplicationCoordinator) {
        self.eligibility = eligibility
        self.coordinator = coordinator
    }

    /// Idempotent desired-state start. Starts NWListener and Bonjour advertisement.
    func start() { fatalError("not implemented") }

    /// Idempotent stop. Cancels listener/connections and removes each remote pairing.
    func stop() { fatalError("not implemented") }

    /// Private boundary: decode wire value, map to domain key/phase, then call admitRemote.
    private func receive(_ bytes: Data, from input: RemoteInputID) {
        fatalError("not implemented")
    }
}

@MainActor
final class ApplicationCoordinator {
    /// One consumer drains eligibility's shared FIFO for both physical and remote admissions.
    private func consumeAdmissions() { fatalError("not implemented") }

    /// The existing physical delegate and remote consumer converge here.
    func handle(_ delivery: AdmittedMediaKey) {
        fatalError("not implemented")
    }

    /// Listener lifecycle is driven by launch, willSleep, didWake, termination.
    private func startRemoteIngress() { fatalError("not implemented") }
    private func stopRemoteIngress() { fatalError("not implemented") }
}
