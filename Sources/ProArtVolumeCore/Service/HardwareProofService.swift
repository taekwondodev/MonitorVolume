import Dispatch

package struct HardwareProofSnapshot: Encodable, Equatable, Sendable {
    package let volume: Int
    package let mute: String

    package init(_ state: ConfirmedMonitorState) {
        volume = state.volume.rawValue
        mute = state.mute == .muted ? "muted" : "unmuted"
    }
}

package struct HardwareProofOutcome: Encodable, Sendable {
    package let confirmed: Bool
    package let writeAttempted: Bool
    package let observed: HardwareProofSnapshot?
    package let error: String?
    package let elapsedNanoseconds: UInt64
}

package struct HardwareProofPhase: Encodable, Sendable {
    package let control: String
    package let initial: HardwareProofSnapshot
    package let requested: HardwareProofSnapshot
    package let transition: HardwareProofOutcome
    package let restorationRequested: HardwareProofSnapshot
    package let restoration: HardwareProofOutcome
}

package struct HardwareProofReport: Encodable, Sendable {
    package let status: String
    package let phases: [HardwareProofPhase]
    package let final: HardwareProofOutcome
}

package actor HardwareProofService {
    private let monitor: any MonitorControlling
    private let output: any ActiveAudioOutputReading
    private var hasRun = false

    package init(monitor: any MonitorControlling, output: any ActiveAudioOutputReading) {
        self.monitor = monitor
        self.output = output
    }

    package func run() async -> HardwareProofReport {
        guard !hasRun else {
            return HardwareProofReport(status: "failed", phases: [], final: .init(
                confirmed: false, writeAttempted: false, observed: nil, error: "proof_already_run", elapsedNanoseconds: 0))
        }
        hasRun = true
        let initial = await read(requireActive: true)
        guard let snapshot = initial.state else {
            return HardwareProofReport(status: "failed", phases: [], final: initial.outcome)
        }
        var phases: [HardwareProofPhase] = []
        for control in [ProofControl.volume, .mute] {
            let requested: ConfirmedMonitorState
            switch control {
            case .volume:
                requested = .init(volume: snapshot.volume.adjusting(by: snapshot.volume.rawValue == 100 ? -1 : 1),
                                  mute: snapshot.mute)
            case .mute:
                requested = .init(volume: snapshot.volume, mute: snapshot.mute.toggled)
            }
            let transition = await write(control, requested: requested)
            let restoration = await write(control, requested: snapshot)
            phases.append(HardwareProofPhase(
                control: control.rawValue, initial: HardwareProofSnapshot(snapshot),
                requested: HardwareProofSnapshot(requested), transition: transition,
                restorationRequested: HardwareProofSnapshot(snapshot), restoration: restoration))
            if !restoration.confirmed { break }
        }
        let final = await read(requireActive: false).outcome
        let passed = phases.count == 2 && phases.allSatisfy { $0.transition.confirmed && $0.restoration.confirmed }
            && final.confirmed && final.observed == HardwareProofSnapshot(snapshot)
        return HardwareProofReport(status: passed ? "passed" : "failed", phases: phases, final: final)
    }

    private enum ProofControl: String { case volume, mute }

    private func write(_ control: ProofControl, requested: ConfirmedMonitorState) async -> HardwareProofOutcome {
        let started = DispatchTime.now().uptimeNanoseconds
        var writeAttempted = false
        do {
            guard try await output.isTargetActive() else {
                return outcome(started: started, error: "inactive_output")
            }
            writeAttempted = true
            switch control {
            case .volume:
                guard try await monitor.writeVolume(requested.volume) == requested.volume else {
                    throw MonitorRepositoryError.readBackMismatch
                }
            case .mute:
                guard try await monitor.writeMute(requested.mute) == requested.mute else {
                    throw MonitorRepositoryError.readBackMismatch
                }
            }
            guard let observed = try await monitor.readState() else {
                return outcome(started: started, error: "unavailable", writeAttempted: true)
            }
            return HardwareProofOutcome(confirmed: observed == requested, writeAttempted: true,
                                        observed: HardwareProofSnapshot(observed),
                                        error: observed == requested ? nil : "readBackMismatch",
                                        elapsedNanoseconds: DispatchTime.now().uptimeNanoseconds - started)
        } catch {
            return outcome(started: started, error: String(describing: error), writeAttempted: writeAttempted)
        }
    }

    private func read(requireActive: Bool) async -> (state: ConfirmedMonitorState?, outcome: HardwareProofOutcome) {
        let started = DispatchTime.now().uptimeNanoseconds
        do {
            if requireActive, try await !output.isTargetActive() {
                return (nil, outcome(started: started, error: "inactive_output"))
            }
            guard let state = try await monitor.readState() else { return (nil, outcome(started: started, error: "unavailable")) }
            return (state, HardwareProofOutcome(confirmed: true, writeAttempted: false,
                                                observed: HardwareProofSnapshot(state), error: nil,
                                                elapsedNanoseconds: DispatchTime.now().uptimeNanoseconds - started))
        } catch {
            return (nil, outcome(started: started, error: String(describing: error)))
        }
    }

    private func outcome(started: UInt64, error: String, writeAttempted: Bool = false) -> HardwareProofOutcome {
        HardwareProofOutcome(confirmed: false, writeAttempted: writeAttempted, observed: nil, error: error,
                             elapsedNanoseconds: DispatchTime.now().uptimeNanoseconds - started)
    }
}
