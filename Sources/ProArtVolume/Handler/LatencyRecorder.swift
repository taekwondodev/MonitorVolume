import CryptoKit
import Foundation
import ProArtVolumeCore
import Synchronization

private struct LatencyEvidenceMetadata: Codable, Sendable {
    let schemaVersion: Int
    let startedAtUTC: String
    let revision: String
    let executablePath: String
    let executableSHA256: String
    let bundleIdentifier: String
    let processIdentifier: Int32
    let monotonicClock: String
    let firstFrameMetric: String
}

private struct LatencyEvidenceEvent: Codable, Sendable {
    let sequence: UInt64
    let uptimeNanoseconds: UInt64
    let stage: LatencyStage
    let interactionIDs: [UInt64]
    let command: LatencyCommand?
    let startingMuted: Bool?
    let outcome: LatencyOutcome?
}

private struct LatencyEvidence: Codable, Sendable {
    let metadata: LatencyEvidenceMetadata
    let events: [LatencyEvidenceEvent]
}

private struct LatencyRecorderState: Sendable {
    var nextSequence: UInt64 = 0
    var nextInteractionID: UInt64 = 0
    var events: [LatencyEvidenceEvent] = []

}

enum LatencyStage: String, Codable, Sendable {
    case sessionStarted = "session_started"
    case inputAccepted = "input_accepted"
    case intentReduced = "intent_reduced"
    case commandEnqueueRequested = "command_enqueue_requested"
    case commandEnqueued = "command_enqueued"
    case serviceCommandStarted = "service_command_started"
    case serviceCommandCompleted = "service_command_completed"
    case commandSuperseded = "command_superseded"
    case commandDiscarded = "command_discarded"
    case activeOutputStarted = "active_output_started"
    case activeOutputCompleted = "active_output_completed"
    case ddcReadStarted = "ddc_read_started"
    case ddcReadCompleted = "ddc_read_completed"
    case ddcWriteReadBackStarted = "ddc_write_read_back_started"
    case ddcWriteReadBackCompleted = "ddc_write_read_back_completed"
    case osdPresentationRequested = "osd_presentation_requested"
    case osdFirstDrawCompleted = "osd_first_draw_completed"
    case osdPresentationSuperseded = "osd_presentation_superseded"
}

enum LatencyCommand: String, Codable, Sendable {
    case volumeUp = "volume_up"
    case volumeDown = "volume_down"
    case toggleMute = "toggle_mute"

    init(_ command: MediaKeyCommand) {
        switch command {
        case .step(.increase):
            self = .volumeUp
        case .step(.decrease):
            self = .volumeDown
        case .toggleMute:
            self = .toggleMute
        }
    }
}

enum LatencyOutcome: String, Codable, Sendable {
    case success
    case failure
}

enum LatencyConfigurationError: LocalizedError {
    case duplicateFlag(String)
    case missingValue(String)
    case destinationMustBeAbsolute
    case destinationMustBeJSON
    case missingDestinationDirectory
    case invalidRevision
    case unreadableExecutable

    var errorDescription: String? {
        switch self {
        case let .duplicateFlag(flag):
            "Duplicate latency option: \(flag)"
        case let .missingValue(flag):
            "Missing value for latency option: \(flag)"
        case .destinationMustBeAbsolute:
            "Latency evidence destination must be an absolute path"
        case .destinationMustBeJSON:
            "Latency evidence destination must use the .json extension"
        case .missingDestinationDirectory:
            "Latency evidence destination directory does not exist"
        case .invalidRevision:
            "Latency revision must be a 40-character hexadecimal commit identifier"
        case .unreadableExecutable:
            "Latency measurement could not read the running executable"
        }
    }
}

final class LatencyRecorder: Sendable {
    private static let evidenceFlag = "--latency-evidence"
    private static let revisionFlag = "--latency-revision"

    private let destination: URL
    private let metadata: LatencyEvidenceMetadata
    private let state = Mutex(LatencyRecorderState())
    private let writer = DispatchQueue(label: "dev.taekwondodev.ProArtVolume.latency-evidence")

    static func configured(arguments: [String] = CommandLine.arguments) throws -> LatencyRecorder? {
        guard let destinationValue = try value(for: evidenceFlag, in: arguments) else {
            return nil
        }
        guard let revision = try value(for: revisionFlag, in: arguments) else {
            throw LatencyConfigurationError.missingValue(revisionFlag)
        }
        guard revision.count == 40, revision.allSatisfy(\.isHexDigit) else {
            throw LatencyConfigurationError.invalidRevision
        }

        guard destinationValue.hasPrefix("/") else {
            throw LatencyConfigurationError.destinationMustBeAbsolute
        }
        let destination = URL(fileURLWithPath: destinationValue)
        guard destination.pathExtension == "json" else {
            throw LatencyConfigurationError.destinationMustBeJSON
        }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(
            atPath: destination.deletingLastPathComponent().path,
            isDirectory: &isDirectory
        ), isDirectory.boolValue else {
            throw LatencyConfigurationError.missingDestinationDirectory
        }

        return try LatencyRecorder(destination: destination, revision: revision)
    }

    private static func value(for flag: String, in arguments: [String]) throws -> String? {
        let matchingIndices = arguments.indices.filter { arguments[$0] == flag }
        guard matchingIndices.count <= 1 else {
            throw LatencyConfigurationError.duplicateFlag(flag)
        }
        guard let flagIndex = matchingIndices.first else {
            return nil
        }
        let valueIndex = arguments.index(after: flagIndex)
        guard valueIndex < arguments.endIndex, !arguments[valueIndex].hasPrefix("--") else {
            throw LatencyConfigurationError.missingValue(flag)
        }
        return arguments[valueIndex]
    }

    private init(destination: URL, revision: String) throws {
        self.destination = destination
        guard let executableURL = Bundle.main.executableURL,
              let executableData = try? Data(contentsOf: executableURL, options: .mappedIfSafe) else {
            throw LatencyConfigurationError.unreadableExecutable
        }
        let executableSHA256 = SHA256.hash(data: executableData)
            .map { String(format: "%02x", $0) }
            .joined()
        metadata = LatencyEvidenceMetadata(
            schemaVersion: 2,
            startedAtUTC: ISO8601DateFormatter().string(from: Date()),
            revision: revision,
            executablePath: executableURL.path,
            executableSHA256: executableSHA256,
            bundleIdentifier: Bundle.main.bundleIdentifier ?? "unknown",
            processIdentifier: ProcessInfo.processInfo.processIdentifier,
            monotonicClock: "DispatchTime.uptimeNanoseconds",
            firstFrameMetric: "NSHostingView.draw_completed"
        )
        try recordSynchronously(stage: .sessionStarted)
    }

    func beginInteraction(command: MediaKeyCommand, startingMuted: Bool?) -> ControlMeasurementID {
        state.withLock { state in
            let timestamp = DispatchTime.now().uptimeNanoseconds
            state.nextInteractionID += 1
            let interactionID = ControlMeasurementID(state.nextInteractionID)

            append(
                stage: .inputAccepted,
                interactionIDs: [interactionID],
                command: LatencyCommand(command),
                startingMuted: startingMuted,
                outcome: nil,
                timestamp: timestamp,
                to: &state
            )
            persist(LatencyEvidence(metadata: metadata, events: state.events))
            return interactionID
        }
    }


    func record(
        stage: LatencyStage,
        context: ControlMeasurementContext? = nil,
        interactionIDs: [ControlMeasurementID] = [],
        outcome: LatencyOutcome? = nil
    ) {
        let effectiveIDs = context?.interactionIDs ?? interactionIDs
        state.withLock { state in
            let timestamp = DispatchTime.now().uptimeNanoseconds
            append(
                stage: stage,
                interactionIDs: effectiveIDs,
                command: nil,
                startingMuted: nil,
                outcome: outcome,
                timestamp: timestamp,
                to: &state
            )
            persist(LatencyEvidence(metadata: metadata, events: state.events))
        }
    }

    func makeServiceObserver() -> ControlMeasurementObserver {
        ControlMeasurementObserver { [self] stage, context in
            let latencyStage: LatencyStage = switch stage {
            case .commandEnqueued:
                .commandEnqueued
            case .commandStarted:
                .serviceCommandStarted
            case .commandCompleted:
                .serviceCommandCompleted
            case .commandSuperseded:
                .commandSuperseded
            case .commandDiscarded:
                .commandDiscarded
            }
            record(stage: latencyStage, context: context)
        }
    }

    private func recordSynchronously(stage: LatencyStage) throws {
        let evidence = state.withLock { state in
            let timestamp = DispatchTime.now().uptimeNanoseconds
            append(
                stage: stage,
                interactionIDs: [],
                command: nil,
                startingMuted: nil,
                outcome: nil,
                timestamp: timestamp,
                to: &state
            )
            return LatencyEvidence(metadata: metadata, events: state.events)
        }
        try Self.write(evidence, to: destination)
    }

    private func append(
        stage: LatencyStage,
        interactionIDs: [ControlMeasurementID],
        command: LatencyCommand?,
        startingMuted: Bool?,
        outcome: LatencyOutcome?,
        timestamp: UInt64,
        to state: inout LatencyRecorderState
    ) {
        state.nextSequence += 1
        state.events.append(
            LatencyEvidenceEvent(
                sequence: state.nextSequence,
                uptimeNanoseconds: timestamp,
                stage: stage,
                interactionIDs: interactionIDs.map(\.rawValue),
                command: command,
                startingMuted: startingMuted,
                outcome: outcome
            )
        )
    }

    private func persist(_ evidence: LatencyEvidence) {
        let destination = destination
        writer.async {
            do {
                try Self.write(evidence, to: destination)
            } catch {
                fatalError("Latency evidence persistence failed: \(error.localizedDescription)")
            }
        }
    }

    private static func write(_ evidence: LatencyEvidence, to destination: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(evidence)
        try data.write(to: destination, options: .atomic)
    }
}
