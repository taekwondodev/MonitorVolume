import Foundation

private struct Observation: Encodable {
    let scenario: String
    let phaseBeforeSignal: String
    let phaseAfterSignal: String
    let generationChangedBySignal: Bool
    let suspensionResult: String
    let wakeResult: String
    let finalPhase: String
    let permissionPolling: Bool
}

@main
private enum OfflinePolicyProbe {
    static func main() throws {
        let reasons: [InputSuspensionReason] = [
            .missingPermission, .permissionRevoked, .tapDisabledByTimeout,
            .tapDisabledByUserInput, .deliveryOverflow, .tapCreationFailed,
        ]
        var observations: [Observation] = []
        let scenarios = [
            "active_sleep_current_signal",
            "unavailable_sleep_current_signal",
            "active_sleep_stale_signal",
            "unavailable_sleep_stale_signal",
            "signal_before_sleep",
        ]
        for reason in reasons {
            for scenario in scenarios {
                let gate = ControlEligibility(capacity: 2)
                if !scenario.hasPrefix("unavailable") {
                    guard case let .started(generation) = gate.reopen(),
                          let volume = VolumeLevel(50) else {
                        throw ProbeError.invalidFixture
                    }
                    gate.publish(ControlSession(
                        generation: generation,
                        seedRevision: 1,
                        seed: ConfirmedMonitorState(volume: volume, mute: .unmuted)
                    ))
                    guard gate.claimTapOwner(generation: generation) else {
                        throw ProbeError.invalidFixture
                    }
                }
                let observedGeneration = gate.generation
                if scenario != "signal_before_sleep" {
                    _ = gate.sleep()
                }
                let signalGeneration = scenario.hasSuffix("current_signal")
                    ? gate.generation
                    : observedGeneration
                let before = String(describing: gate.phase)
                let generation = gate.generation
                let result = gate.suspend(reason, observedGeneration: signalGeneration)
                let after = String(describing: gate.phase)
                let changed = gate.generation != generation
                if scenario == "signal_before_sleep" {
                    _ = gate.sleep()
                }
                gate.releaseTap()
                let wake = gate.wake()
                observations.append(Observation(
                    scenario: "\(scenario):\(reason)",
                    phaseBeforeSignal: before,
                    phaseAfterSignal: after,
                    generationChangedBySignal: changed,
                    suspensionResult: String(describing: result),
                    wakeResult: String(describing: wake),
                    finalPhase: String(describing: gate.phase),
                    permissionPolling: gate.allowsPermissionPolling
                ))
            }
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(observations)
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
    }

    private enum ProbeError: Error {
        case invalidFixture
    }
}
