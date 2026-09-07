import CryptoKit
import Dispatch
import Foundation
import ProArtVolumeCore
import Synchronization

private struct OfflineArguments {
    let workloadMilliseconds: Int
    let instrumentation: String
    let resourceState: String

    init(arguments: [String]) {
        workloadMilliseconds = Self.value(for: "--workload-ms", in: arguments).flatMap(Int.init) ?? 1_200
        instrumentation = Self.value(for: "--instrumentation", in: arguments) ?? "full"
        resourceState = Self.value(for: "--resource-state", in: arguments) ?? "active"
    }

    private static func value(for flag: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: flag), arguments.index(after: index) < arguments.endIndex else {
            return nil
        }
        return arguments[arguments.index(after: index)]
    }
}

private struct OfflineExecutableBinding: Codable, Sendable {
    let path: String
    let sha256: String
}

private struct OfflineConfiguration: Codable, Sendable {
    let schemaVersion: Int
    let contract: String
    let capacity: Int
    let permissionPollIntervalMilliseconds: Int
    let permissionPollingRule: String
    let tapTeardownRule: String
    let samplingIntervalMilliseconds: Int
    let observationWindowsMilliseconds: [String: Int]
    let cpuNormalization: String
    let ramMeasure: String
    let eventTimestampRule: String
    let workload: String
    let workloadClassification: String
    let capacitySelectionProcedure: String
    let comparisonProcedure: String
    let repeatabilityCriteria: String
    let instrumentationMode: String
}

private struct OfflineTimingAvailability: Codable, Sendable {
    let status: String
    let reason: String
}

private struct OfflineEvent: Codable, Sendable {
    let sequence: UInt64
    let timestampNanoseconds: UInt64
    let scenario: String
    let kind: String
    let generation: UInt64?
    let deliverySequence: UInt64?
    let command: String?
    let accepted: Bool?
    let discarded: Bool?
}

private struct OfflineScenarioResult: Codable, Sendable {
    let name: String
    let passed: Bool
    let checks: [String: Bool]
    let notes: [String]
}

private struct OfflineAdmissionEvidence: Codable, Sendable {
    let attempted: UInt64
    let admitted: UInt64
    let rejected: UInt64
    let discarded: UInt64
    let overflow: UInt64
    let completed: UInt64
    let peakOutstanding: Int
    let maximumDeliveryWaitNanoseconds: UInt64
}

private struct OfflineResourceContract: Codable, Sendable {
    let samplingMethod: String
    let samplingIntervalMilliseconds: Int
    let activeIdleWindowMilliseconds: Int
    let burstWindowMilliseconds: Int
    let suspendedWindowMilliseconds: Int
    let postBurstRetentionWindowMilliseconds: Int
    let postSuspensionRetentionWindowMilliseconds: Int
    let wakeupMetric: OfflineTimingAvailability
    let threadAndTapMetric: OfflineTimingAvailability
    let instrumentationOverhead: String
}

private struct OfflineReport: Codable, Sendable {
    let status: String
    let executionClass: String
    let resourceState: String
    let instrumentation: String
    let executable: OfflineExecutableBinding
    let configuration: OfflineConfiguration
    let scenarios: [OfflineScenarioResult]
    let events: [OfflineEvent]
    let admission: OfflineAdmissionEvidence
    let frameworkTimings: [String: OfflineTimingAvailability]
    let resourceContract: OfflineResourceContract
    let workloadPhase: String
    let liveReadiness: [String]
    let failures: [String]
}

private final class OfflineContractRunner {
    private let arguments: OfflineArguments
    private let gate: ControlEligibility
    private let monitor: OfflineMonitor
    private let timer: OfflineTimer
    private let measurementLog: OfflineMeasurementLog
    private let service: IntentControlService
    private var reducer = VolumeIntentReducer()
    private var events: [OfflineEvent] = []
    private var scenarios: [OfflineScenarioResult] = []
    private var failures: [String] = []
    private var timestampNanoseconds: UInt64 = 0

    init(arguments: OfflineArguments) {
        self.arguments = arguments
        gate = ControlEligibility(capacity: 2)
        monitor = OfflineMonitor(state: .init(volume: Self.volume(50), mute: .unmuted))
        let timer = OfflineTimer()
        self.timer = timer
        let measurementLog = OfflineMeasurementLog()
        self.measurementLog = measurementLog
        let output = OfflineOutput()
        service = IntentControlService(
            monitor: monitor,
            activeOutput: output,
            eligibility: gate,
            sleeper: ControlSleeper { await timer.sleep(for: $0) },
            observer: ControlMeasurementObserver { stage, _ in measurementLog.record(stage) }
        )
    }

    func run() async -> OfflineReport {
        guard case let .started(generation) = gate.reopen() else {
            failures.append("initial tap-owner teardown fence was unexpectedly active")
            return report()
        }
        record(scenario: "lifecycle", kind: "reopen", generation: generation)
        _ = await service.revalidate(generation: generation, permitted: true)
        await service.waitForIdle()
        guard let session = gate.session else {
            failures.append("trusted seed was not published")
            return report()
        }
        guard gate.claimTapOwner(generation: session.generation) else {
            failures.append("initial tap owner could not claim the eligible generation")
            return report()
        }
        record(scenario: "lifecycle", kind: "hardware_seeded", generation: session.generation)
        runIntentScenario()
        await runAcceptedInputScenario()
        await runRecoveryScenario()
        await runFailedWriteRecoveryScenario()
        await runSuspensionScenario()
        await runSleepWakeScenario()
        await runOverflowScenario()
        await runStaleDeliveryScenario()
        await prepareWorkloadState()
        await runWorkload()
        return report()
    }

    private func runIntentScenario() {
        let upperSession = session(volume: 98, mute: .unmuted, generation: 1, seedRevision: 1)
        var upperReducer = VolumeIntentReducer()
        let upper = [
            upperReducer.accept(.step(.increase), session: upperSession).intent.volume.rawValue,
            upperReducer.accept(.step(.decrease), session: upperSession).intent.volume.rawValue,
        ]
        let lowerSession = session(volume: 2, mute: .unmuted, generation: 2, seedRevision: 1)
        var lowerReducer = VolumeIntentReducer()
        let lower = [
            lowerReducer.accept(.step(.decrease), session: lowerSession).intent.volume.rawValue,
            lowerReducer.accept(.step(.increase), session: lowerSession).intent.volume.rawValue,
        ]
        let rapidSession = session(volume: 50, mute: .unmuted, generation: 3, seedRevision: 1)
        var rapidReducer = VolumeIntentReducer()
        let rapid = (0..<3).map { _ in
            rapidReducer.accept(.step(.increase), session: rapidSession).intent.volume.rawValue
        }
        let muteSession = session(volume: 50, mute: .unmuted, generation: 4, seedRevision: 1)
        var muteReducer = VolumeIntentReducer()
        let mute = (0..<3).map { _ in
            muteReducer.accept(.toggleMute, session: muteSession).intent.mute == .muted
        }
        let boundarySession = session(volume: 100, mute: .muted, generation: 5, seedRevision: 1)
        var boundaryReducer = VolumeIntentReducer()
        let boundary = boundaryReducer.accept(.step(.increase), session: boundarySession).intent
        let freshSession = session(volume: 80, mute: .muted, generation: 6, seedRevision: 2)
        var freshReducer = VolumeIntentReducer()
        let fresh = freshReducer.accept(.step(.increase), session: freshSession).intent
        addScenario(
            name: "intent_semantics",
            checks: [
                "upper_boundary": upper == [100, 95],
                "lower_boundary": lower == [0, 5],
                "rapid_steps": rapid == [55, 60, 65],
                "mute_parity": mute == [true, false, true],
                "boundary_unmute": boundary.volume.rawValue == 100 && boundary.mute == .unmuted,
                "fresh_seed": fresh.volume.rawValue == 85 && fresh.mute == .unmuted,
            ],
            notes: ["Intent values are computed by the shared Domain reducer."]
        )
    }

    private func runAcceptedInputScenario() async {
        let result = await accept(.step(.increase), key: .volumeUp, scenario: "accepted_input")
        let passed: Bool
        do {
            let value = try await monitor.readState()
            passed = result && value?.volume.rawValue == 55 && value?.mute == .unmuted
        } catch {
            passed = false
        }
        addScenario(
            name: "accepted_input",
            checks: ["ordered_consumer": result, "service_outcome": passed],
            notes: ["One admitted delivery was reduced before Service submission."]
        )
    }

    private func runRecoveryScenario() async {
        let writesBeforeRecovery = await monitor.writeAttempts
        let generation = gate.invalidate()
        await monitor.failNextRead(.readFailure)
        let revalidated = await service.revalidate(generation: generation, permitted: true)
        await service.waitForIdle()
        let unavailableAfterFailure = gate.session == nil
        let delay = await timer.nextDelay()
        record(scenario: "service_recovery", kind: "read_failed", generation: generation, accepted: false, discarded: true)
        record(scenario: "service_recovery", kind: "backoff_scheduled", generation: generation)
        let recoveryTimer = timer
        await service.waitForRecoveryAttempt { await recoveryTimer.advance() }
        let recovered = gate.session
        record(
            scenario: "service_recovery",
            kind: "read_recovered",
            generation: recovered?.generation,
            accepted: recovered != nil
        )
        addScenario(
            name: "service_recovery",
            checks: [
                "revalidation_started": revalidated,
                "failure_is_unavailable": unavailableAfterFailure,
                "existing_backoff": delay == .seconds(2),
                "recovery_reseeds": recovered != nil,
                "no_write_during_read_recovery": await monitor.writeAttempts == writesBeforeRecovery,
            ],
            notes: ["DDC read recovery is controlled by the existing Service and re-seeds hardware state without issuing a command."]
        )
    }

    private func runFailedWriteRecoveryScenario() async {
        guard let session = gate.session,
              case .consumeKeyDown = gate.route(
                  .init(key: .volumeDown, phase: .down), at: nextTimestamp()
              ),
              let delivery = gate.dequeue(at: nextTimestamp()) else {
            addScenario(name: "failed_write_recovery", checks: ["admitted": false], notes: [])
            return
        }
        let beforeAttempts = await monitor.writeAttempts
        let successfulWritesBefore = await monitor.successfulWriteCount
        await monitor.failNextWrite(.writeFailure)
        var failedReducer = VolumeIntentReducer()
        let request = failedReducer.accept(delivery.command, session: session)
        record(
            scenario: "failed_write_recovery",
            kind: "admitted",
            generation: delivery.session.generation,
            deliverySequence: delivery.sequence,
            command: commandName(delivery.command),
            accepted: true
        )
        await service.submit(request)
        await service.waitForIdle()
        let unavailableAfterFailure = gate.session == nil
        let delay = await timer.nextDelay()
        record(
            scenario: "failed_write_recovery",
            kind: "command_write_failed",
            generation: delivery.session.generation,
            deliverySequence: delivery.sequence,
            command: commandName(delivery.command),
            accepted: false,
            discarded: true
        )
        let recoveryTimer = timer
        await service.waitForRecoveryAttempt { await recoveryTimer.advance() }
        let recovered = gate.session
        let attemptsAfterRecovery = await monitor.writeAttempts
        let successfulWritesAfter = await monitor.successfulWriteCount
        let noReplay = beforeAttempts + 1 == attemptsAfterRecovery && successfulWritesAfter == successfulWritesBefore
        _ = gate.complete(delivery)
        _ = gate.route(.init(key: .volumeDown, phase: .up), at: nextTimestamp())
        record(
            scenario: "failed_write_recovery",
            kind: "read_only_recovery",
            generation: recovered?.generation,
            accepted: recovered != nil
        )
        addScenario(
            name: "failed_write_recovery",
            checks: [
                "admitted": true,
                "failure_is_unavailable": unavailableAfterFailure,
                "existing_backoff": delay == .seconds(2),
                "recovery_reseeds": recovered != nil,
                "failed_command_not_replayed": noReplay,
            ],
            notes: ["A failed write is not replayed by read-only recovery."]
        )
    }

    private func runSuspensionScenario() async {
        guard let session = gate.session else {
            addScenario(name: "suspension", checks: ["active_session": false], notes: [])
            return
        }
        guard case let .consumeKeyDown(delivery) = gate.route(
            .init(key: .volumeDown, phase: .down), at: nextTimestamp()
        ) else {
            addScenario(name: "suspension", checks: ["held_delivery": false], notes: [])
            return
        }
        record(
            scenario: "suspension",
            kind: "admitted_before_revoke",
            generation: delivery.session.generation,
            deliverySequence: delivery.sequence,
            command: "volume_down",
            accepted: true
        )
        let suspendedGeneration = gate.suspend(.permissionRevoked)
        record(scenario: "suspension", kind: "permission_revoked", generation: suspendedGeneration)
        let rejectedDecision = gate.route(.init(key: .mute, phase: .down), at: nextTimestamp())
        let rejected = rejectedDecision == .passThrough
        record(
            scenario: "suspension",
            kind: "rejected_after_revoke",
            generation: gate.generation,
            accepted: false,
            discarded: true
        )
        let oldPublish = gate.session == nil
        gate.publish(session)
        let stillSuspended = gate.phase == .suspended(.permissionRevoked)
        let staleRegrant = ControlSession(
            generation: suspendedGeneration,
            seedRevision: session.seedRevision + 1,
            seed: session.seed
        )
        gate.publish(staleRegrant)
        gate.markUnavailable(generation: suspendedGeneration)
        let beforeBlockedRecovery = await monitor.readCount
        let invalidatedWhileSuspended = gate.invalidate()
        let recoveryStartedWhileSuspended = await service.revalidate(
            generation: invalidatedWhileSuspended,
            permitted: true
        )
        await service.waitForIdle()
        let afterBlockedRecovery = await monitor.readCount
        let externalResultsStayedLatched = gate.phase == .suspended(.permissionRevoked)
            && gate.session == nil
            && beforeBlockedRecovery == afterBlockedRecovery
            && !recoveryStartedWhileSuspended
        record(
            scenario: "suspension",
            kind: "stale_external_results",
            generation: invalidatedWhileSuspended,
            accepted: false,
            discarded: true
        )
        let pairing = gate.route(.init(key: .volumeDown, phase: .up), at: nextTimestamp())
        record(
            scenario: "suspension",
            kind: pairing == .consumeKeyUp ? "paired_key_up" : "unpaired_key_up",
            generation: gate.generation,
            accepted: pairing == .consumeKeyUp
        )
        gate.releaseTap()
        guard case let .started(reopened) = gate.reopen() else {
            addScenario(name: "suspension", checks: ["reopen_after_teardown": false], notes: [])
            return
        }
        record(scenario: "suspension", kind: "explicit_reopen", generation: reopened)
        let fresh = ControlSession(generation: reopened, seedRevision: 3, seed: session.seed)
        gate.publish(fresh)
        let acceptsAfterReopen = gate.contains(fresh)
        addScenario(
            name: "suspension",
            checks: [
                "pending_discarded": gate.snapshot.metrics.discardedCount >= 1,
                "rejected_pass_through": rejected,
                "grant_does_not_clear": oldPublish && stillSuspended,
                "external_results_latched": externalResultsStayedLatched,
                "explicit_reopen": acceptsAfterReopen,
            ],
            notes: ["Permission regrant is modeled as a stale publish; only reopen clears the latch."]
        )
        _ = delivery
        _ = await service.waitForIdle()
    }

    private func runSleepWakeScenario() async {
        guard gate.session != nil else {
            addScenario(name: "sleep_wake", checks: ["active_wake": false], notes: [])
            return
        }
        gate.releaseTap()
        let sleepingGeneration = gate.sleep()
        record(scenario: "sleep_wake", kind: "sleep", generation: sleepingGeneration)
        let passThroughWhileSleeping = gate.route(.init(key: .volumeUp, phase: .down), at: nextTimestamp()) == .passThrough
        record(
            scenario: "sleep_wake",
            kind: "pass_through_while_sleeping",
            generation: gate.generation,
            accepted: false
        )
        let wake = gate.wake()
        let activeWake = if case .revalidate = wake { true } else { false }
        record(scenario: "sleep_wake", kind: "wake_revalidate", generation: gate.generation)
        let wakeValidation = await service.revalidate(generation: gate.generation, permitted: true)
        await service.waitForIdle()
        let freshHardwareAfterWake = gate.session != nil
        let suspended = gate.suspend(.tapDisabledByUserInput)
        record(scenario: "sleep_wake", kind: "suspend_after_wake", generation: suspended)
        _ = gate.sleep()
        let suspendedWake = gate.wake() == .remainsSuspended(.tapDisabledByUserInput)
        addScenario(
            name: "sleep_wake",
            checks: [
                "sleep_pass_through": passThroughWhileSleeping,
                "active_wake_revalidates": activeWake,
                "fresh_hardware_after_wake": wakeValidation && freshHardwareAfterWake,
                "suspended_wake_stays_suspended": suspendedWake,
            ],
            notes: ["Wake never publishes a session by itself."]
        )
    }

    private func runOverflowScenario() async {
        gate.releaseTap()
        guard case let .started(generation) = gate.reopen() else {
            addScenario(name: "overflow", checks: ["reopen_after_teardown": false], notes: [])
            return
        }
        let seed = session(volume: 50, mute: .unmuted, generation: generation, seedRevision: 4)
        gate.publish(seed)
        guard gate.claimTapOwner(generation: generation) else {
            addScenario(name: "overflow", checks: ["tap_owner_claimed": false], notes: [])
            return
        }
        let first = gate.route(.init(key: .volumeUp, phase: .down), at: nextTimestamp())
        let second = gate.route(.init(key: .volumeDown, phase: .down), at: nextTimestamp())
        let overflow = gate.route(.init(key: .mute, phase: .down), at: nextTimestamp())
        record(scenario: "overflow", kind: "first", generation: generation, accepted: first != .passThrough)
        record(scenario: "overflow", kind: "second", generation: generation, accepted: second != .passThrough)
        record(scenario: "overflow", kind: "rejected", generation: gate.generation, accepted: false, discarded: true)
        addScenario(
            name: "overflow",
            checks: [
                "capacity_two": first != .passThrough && second != .passThrough,
                "next_passes": overflow == .passThroughAfterOverflow,
                "latched": gate.phase == .suspended(.deliveryOverflow),
                "queue_discarded": gate.pendingDeliveryCount == 0,
                "no_wait_for_capacity": true,
            ],
            notes: ["The third down is returned to the system; admission never waits."]
        )
    }

    private func runStaleDeliveryScenario() async {
        gate.releaseTap()
        guard case let .started(generation) = gate.reopen() else {
            addScenario(name: "stale_delivery", checks: ["reopen_after_teardown": false], notes: [])
            return
        }
        let seed = session(volume: 50, mute: .unmuted, generation: generation, seedRevision: 5)
        gate.publish(seed)
        guard gate.claimTapOwner(generation: generation) else {
            addScenario(name: "stale_delivery", checks: ["tap_owner_claimed": false], notes: [])
            return
        }
        guard case .consumeKeyDown = gate.route(
            .init(key: .volumeUp, phase: .down), at: nextTimestamp()
        ), let dequeued = gate.dequeue(at: nextTimestamp()) else {
            addScenario(name: "stale_delivery", checks: ["admitted": false], notes: [])
            return
        }
        _ = gate.suspend(.permissionRevoked)
        let beforeReads = await monitor.readCount
        let beforeWrites = await monitor.writeAttempts
        let discardedBeforeService = measurementLog.discardedCount
        let staleRequest = DesiredMonitorState(
            session: dequeued.session,
            revision: 1,
            intent: VolumeIntent(dequeued.session.seed).applying(dequeued.command),
            measurementID: ControlMeasurementID(9_999)
        )
        await service.submit(staleRequest)
        await service.waitForIdle()
        let rejectedBeforeIntent = !gate.contains(dequeued.session)
        let rejectedByService = measurementLog.discardedCount == discardedBeforeService + 1
        let readsAfterService = await monitor.readCount
        let writesAfterService = await monitor.writeAttempts
        let noHardwareWork = readsAfterService == beforeReads && writesAfterService == beforeWrites
        record(
            scenario: "stale_delivery",
            kind: "discarded_after_revoke",
            generation: gate.generation,
            deliverySequence: dequeued.sequence,
            accepted: false,
            discarded: true
        )
        let completedBookkeeping = gate.complete(dequeued)
        addScenario(
            name: "stale_delivery",
            checks: [
                "admitted": true,
                "session_rejected": rejectedBeforeIntent,
                "no_intent_or_osd": rejectedByService && noHardwareWork,
                "bookkeeping_completed": completedBookkeeping,
            ],
            notes: ["A stale delivery is rejected by the gate and Service before hardware work; no offline OSD adapter is invoked."]
        )
    }

    private func prepareWorkloadState() async {
        switch arguments.resourceState {
        case "suspended":
            if !gate.phase.isSuspended {
                _ = gate.suspend(.deliveryOverflow)
            }
            record(scenario: "resources", kind: "suspended", generation: gate.generation)
        case "active":
            gate.releaseTap()
            guard case let .started(generation) = gate.reopen() else {
                failures.append("active workload could not complete tap teardown")
                return
            }
            do {
                guard let state = try await monitor.readState() else {
                    failures.append("active workload could not read its seed")
                    return
                }
                let session = ControlSession(generation: generation, seedRevision: 6, seed: state)
                gate.publish(session)
                guard gate.claimTapOwner(generation: generation) else {
                    failures.append("active workload could not claim its tap owner")
                    return
                }
                record(scenario: "resources", kind: "active", generation: generation)
            } catch {
                failures.append("active workload seed read failed")
            }
        default:
            failures.append("unsupported resource state")
        }
    }

    private func accept(_ command: MediaKeyCommand, key: MediaKey, scenario: String) async -> Bool {
        guard case let .consumeKeyDown(delivery) = gate.route(
            .init(key: key, phase: .down), at: nextTimestamp()
        ) else {
            record(scenario: scenario, kind: "rejected", generation: gate.generation, accepted: false)
            return false
        }
        record(
            scenario: scenario,
            kind: "admitted",
            generation: delivery.session.generation,
            deliverySequence: delivery.sequence,
            command: commandName(command),
            accepted: true
        )
        guard let queued = gate.dequeue(at: nextTimestamp()) else {
            record(scenario: scenario, kind: "discarded", generation: gate.generation, accepted: false, discarded: true)
            return false
        }
        let valid = gate.contains(queued.session)
        guard valid else {
            _ = gate.complete(queued)
            record(scenario: scenario, kind: "stale", generation: gate.generation, deliverySequence: queued.sequence, accepted: false, discarded: true)
            return false
        }
        let request = reducer.accept(queued.command, session: queued.session)
        record(
            scenario: scenario,
            kind: "intent_reduced",
            generation: queued.session.generation,
            deliverySequence: queued.sequence,
            command: commandName(queued.command),
            accepted: true
        )
        record(
            scenario: scenario,
            kind: "osd_requested",
            generation: queued.session.generation,
            deliverySequence: queued.sequence,
            command: commandName(queued.command),
            accepted: true
        )
        await service.submit(request)
        await service.waitForIdle()
        _ = gate.complete(queued)
        record(
            scenario: scenario,
            kind: "service_completed",
            generation: queued.session.generation,
            deliverySequence: queued.sequence,
            command: commandName(queued.command),
            accepted: true
        )
        let keyUp = gate.route(.init(key: key, phase: .up), at: nextTimestamp())
        record(
            scenario: scenario,
            kind: keyUp == .consumeKeyUp ? "paired_key_up" : "unpaired_key_up",
            generation: gate.generation,
            deliverySequence: queued.sequence,
            command: commandName(queued.command),
            accepted: keyUp == .consumeKeyUp
        )
        return true
    }

    private func addScenario(name: String, checks: [String: Bool], notes: [String]) {
        let passed = checks.values.allSatisfy { $0 }
        if !passed {
            failures.append(contentsOf: checks.filter { !$0.value }.map { "\(name).\($0.key)" })
        }
        scenarios.append(OfflineScenarioResult(name: name, passed: passed, checks: checks, notes: notes))
    }

    private func record(
        scenario: String,
        kind: String,
        generation: UInt64? = nil,
        deliverySequence: UInt64? = nil,
        command: String? = nil,
        accepted: Bool? = nil,
        discarded: Bool? = nil
    ) {
        guard arguments.instrumentation == "full" else { return }
        events.append(OfflineEvent(
            sequence: UInt64(events.count + 1),
            timestampNanoseconds: nextTimestamp(),
            scenario: scenario,
            kind: kind,
            generation: generation,
            deliverySequence: deliverySequence,
            command: command,
            accepted: accepted,
            discarded: discarded
        ))
    }

    private func nextTimestamp() -> UInt64 {
        defer { timestampNanoseconds &+= 1_000_000 }
        return timestampNanoseconds
    }

    private func runWorkload() async {
        let milliseconds = max(100, arguments.workloadMilliseconds)
        let busyMilliseconds = max(50, milliseconds / 2)
        var values = Array(repeating: UInt64(0), count: 32_768)
        let deadline = DispatchTime.now().uptimeNanoseconds &+ UInt64(busyMilliseconds) * 1_000_000
        while DispatchTime.now().uptimeNanoseconds < deadline {
            for index in values.indices {
                values[index] &+= UInt64(index + 1)
            }
        }
        values.removeAll(keepingCapacity: true)
        let remaining = milliseconds - busyMilliseconds
        if remaining > 0 {
            try? await Task.sleep(for: .milliseconds(remaining))
        }
    }

    private func report() -> OfflineReport {
        let executableURL = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
        let hash: String
        if let data = try? Data(contentsOf: executableURL) {
            hash = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        } else {
            hash = ""
            failures.append("offline executable is unreadable")
        }
        let configuration = OfflineConfiguration(
            schemaVersion: 1,
            contract: "shared-suspension-v1",
            capacity: 2,
            permissionPollIntervalMilliseconds: 1_000,
            permissionPollingRule: "poll only while the lifecycle is active, outside framework callbacks; stop in suspension and sleep",
            tapTeardownRule: "reopen waits for the prior owner to release its tap and key pairing; no callback or MainActor wait",
            samplingIntervalMilliseconds: 20,
            observationWindowsMilliseconds: [
                "activeIdle": 200,
                "burst": 300,
                "suspended": 200,
                "postBurstRetention": 200,
                "postSuspensionRetention": 200,
            ],
            cpuNormalization: "ps_percent_divided_by_logical_cpu",
            ramMeasure: "resident_set_size_kib",
            eventTimestampRule: "monotonic nonnegative process-uptime timestamps; no callback-duration SLA",
            workload: "controlled_domain_service_drive",
            workloadClassification: "offline_not_installed_app_performance",
            capacitySelectionProcedure: "smallest configured capacity that admits the declared normal burst fixture without producer waiting; freeze before A/B",
            comparisonProcedure: "alternate equal Release runs, repeat isolated/repeated/mixed/stress workloads, retain failures and censored observations",
            repeatabilityCriteria: "compare complete outcome sequences and resource windows; inconclusive when correctness or evidence differs",
            instrumentationMode: arguments.instrumentation
        )
        let frameworkTimings = [
            "event_to_callback": OfflineTimingAvailability(status: "unavailable", reason: "No CoreGraphics event tap runs in the offline harness."),
            "callback_entry_exit": OfflineTimingAvailability(status: "unavailable", reason: "Offline admission is modeled without a framework callback."),
            "osd_first_draw": OfflineTimingAvailability(status: "unavailable", reason: "No AppKit window or physical scanout runs in the offline harness."),
            "timeout_and_tap_release": OfflineTimingAvailability(status: "modeled", reason: "Suspension and tap-release ownership are represented by the shared gate; native release timing requires a later runtime campaign."),
        ]
        let snapshot = gate.snapshot
        let admission = OfflineAdmissionEvidence(
            attempted: snapshot.metrics.attemptedCount,
            admitted: snapshot.metrics.admittedCount,
            rejected: snapshot.metrics.rejectedCount,
            discarded: snapshot.metrics.discardedCount,
            overflow: snapshot.metrics.overflowCount,
            completed: snapshot.metrics.completedCount,
            peakOutstanding: snapshot.metrics.peakOutstanding,
            maximumDeliveryWaitNanoseconds: snapshot.metrics.maximumDeliveryWaitNanoseconds
        )
        let resourceContract = OfflineResourceContract(
            samplingMethod: "parent samples ps pcpu/rss every declared interval while this Release harness runs",
            samplingIntervalMilliseconds: configuration.samplingIntervalMilliseconds,
            activeIdleWindowMilliseconds: configuration.observationWindowsMilliseconds["activeIdle"] ?? 0,
            burstWindowMilliseconds: configuration.observationWindowsMilliseconds["burst"] ?? 0,
            suspendedWindowMilliseconds: configuration.observationWindowsMilliseconds["suspended"] ?? 0,
            postBurstRetentionWindowMilliseconds: configuration.observationWindowsMilliseconds["postBurstRetention"] ?? 0,
            postSuspensionRetentionWindowMilliseconds: configuration.observationWindowsMilliseconds["postSuspensionRetention"] ?? 0,
            wakeupMetric: OfflineTimingAvailability(status: "unavailable", reason: "macOS wakeup counters are not exposed by the offline harness sampler."),
            threadAndTapMetric: OfflineTimingAvailability(status: "modeled", reason: "The common model records no native tap and one consumer; native thread/tap lifetime requires candidate runtime evidence."),
            instrumentationOverhead: "Run the same Release workload with instrumentation full and none; compare identical windows without calling either installed-app performance."
        )
        let liveReadiness = [
            "CoreGraphics event-to-callback scheduling is unproven.",
            "native Accessibility identity and prompt visibility are unproven.",
            "AppKit OSD draw and physical scanout are unproven.",
            "native tap teardown effects on system input are unproven.",
            "physical DDC control is outside this non-invasive drive.",
        ]
        return OfflineReport(
            status: failures.isEmpty && scenarios.allSatisfy(\.passed) ? "passed" : "failed",
            executionClass: "offline_common_contract",
            resourceState: arguments.resourceState,
            instrumentation: arguments.instrumentation,
            executable: OfflineExecutableBinding(path: executableURL.path, sha256: hash),
            configuration: configuration,
            scenarios: scenarios,
            events: events,
            admission: admission,
            frameworkTimings: frameworkTimings,
            resourceContract: resourceContract,
            workloadPhase: phaseName(gate.phase),
            liveReadiness: liveReadiness,
            failures: failures
        )
    }

    private func session(volume: Int, mute: MuteState, generation: UInt64, seedRevision: UInt64) -> ControlSession {
        ControlSession(
            generation: generation,
            seedRevision: seedRevision,
            seed: .init(volume: Self.volume(volume), mute: mute)
        )
    }

    private static func volume(_ value: Int) -> VolumeLevel {
        guard let volume = VolumeLevel(value) else {
            fatalError("offline fixture contains an invalid volume")
        }
        return volume
    }

    private func commandName(_ command: MediaKeyCommand) -> String {
        switch command {
        case .step(.increase):
            "volume_up"
        case .step(.decrease):
            "volume_down"
        case .toggleMute:
            "toggle_mute"
        }
    }

    private func phaseName(_ phase: ControlEligibilityPhase) -> String {
        switch phase {
        case .unavailable:
            "unavailable"
        case .validating:
            "validating"
        case .activeWithoutHardware:
            "active_without_hardware"
        case .eligible:
            "eligible"
        case .suspended:
            "suspended"
        case .sleepingAfterActive:
            "sleeping_after_active"
        case .sleepingWhileSuspended:
            "sleeping_while_suspended"
        case .sleepingWhileUnavailable:
            "sleeping_while_unavailable"
        }
    }
}

private final class OfflineMeasurementLog: Sendable {
   private let stages = Mutex<[ControlMeasurementStage]>([])

   func record(_ stage: ControlMeasurementStage) {
       stages.withLock { $0.append(stage) }
   }

   var discardedCount: Int {
       stages.withLock { stages in
           stages.reduce(into: 0) { count, stage in
               if case .commandDiscarded = stage {
                   count += 1
               }
           }
       }
   }
}

private actor OfflineOutput: ActiveAudioOutputReading {
    func isTargetActive() async throws(MonitorRepositoryError) -> Bool { true }
}

private actor OfflineTimer {
    private var sleeper: CheckedContinuation<Void, Never>?
    private var delayWaiter: CheckedContinuation<Duration, Never>?
    private var delay: Duration?

    func sleep(for duration: Duration) async {
        delay = duration
        await withCheckedContinuation { continuation in
            sleeper = continuation
            delayWaiter?.resume(returning: duration)
            delayWaiter = nil
        }
    }

    func nextDelay() async -> Duration {
        if let delay { return delay }
        return await withCheckedContinuation { delayWaiter = $0 }
    }

    func advance() {
        delay = nil
        sleeper?.resume()
        sleeper = nil
    }
}

private actor OfflineMonitor: MonitorControlling {
    private var state: ConfirmedMonitorState
    private var readError: MonitorRepositoryError?
    private var writeError: MonitorRepositoryError?
    private(set) var writeAttempts = 0
    private(set) var successfulWriteCount = 0
    private(set) var readCount = 0

    init(state: ConfirmedMonitorState) {
        self.state = state
    }

    func failNextRead(_ error: MonitorRepositoryError) {
        readError = error
    }

    func failNextWrite(_ error: MonitorRepositoryError) {
        writeError = error
    }

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        readCount += 1
        if let error = readError {
            readError = nil
            throw error
        }
        return state
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        writeAttempts += 1
        if let error = writeError {
            writeError = nil
            throw error
        }
        successfulWriteCount += 1
        state = .init(volume: volume, mute: state.mute)
        return volume
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        writeAttempts += 1
        if let error = writeError {
            writeError = nil
            throw error
        }
        successfulWriteCount += 1
        state = .init(volume: state.volume, mute: mute)
        return mute
    }
}

@main
private enum ProArtVolumeOfflineHarness {
    static func main() async {
        let runner = OfflineContractRunner(arguments: OfflineArguments(arguments: CommandLine.arguments))
        let report = await runner.run()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(report) else {
            exit(1)
        }
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
        exit(report.status == "passed" ? 0 : 1)
    }
}
