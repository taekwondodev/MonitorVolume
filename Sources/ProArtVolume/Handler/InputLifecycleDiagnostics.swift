import Foundation
import OSLog

@MainActor
final class InputLifecycleDiagnostics {
    private let logger = Logger(subsystem: "dev.taekwondodev.ProArtVolume", category: "input-lifecycle")
    private var budget = InputLifecycleBudget()

    static func configured(arguments: [String] = CommandLine.arguments) -> InputLifecycleDiagnostics? {
        switch InputLifecycleConfiguration(arguments: arguments) {
        case .disabled:
            return nil
        case .enabled:
            let diagnostics = InputLifecycleDiagnostics()
            diagnostics.record(.sessionStarted)
            return diagnostics
        case .duplicateFlag:
            Logger(subsystem: "dev.taekwondodev.ProArtVolume", category: "input-lifecycle")
                .error("schema=1 event=configurationUnavailable reason=duplicateFlag")
            return nil
        }
    }

    private init() {}

    func begin(_ kind: InputLifecycleOperation, tap: UInt64 = 0,
               reason: InputLifecycleReason) -> InputLifecycleOperationToken? {
        guard budget.acceptsRegularRecord else {
            record(.budgetExhausted)
            return nil
        }
        let sequence = budget.sequence + 1
        let token = InputLifecycleOperationToken(sequence: sequence, kind: kind, tap: kind == .tapCreate ? sequence : tap)
        record(.operationBegan(token, reason))
        return token
    }

    func end(_ token: InputLifecycleOperationToken?, result: InputLifecycleOperationResult = .returned) {
        guard let token else { return }
        record(.operationEnded(token, result))
    }

    func beginQuery(_ kind: InputLifecycleQuery, tap: UInt64 = 0) -> InputLifecycleQueryToken? {
        guard budget.acceptsRegularRecord else {
            record(.budgetExhausted)
            return nil
        }
        let token = InputLifecycleQueryToken(sequence: budget.sequence + 1, kind: kind, tap: tap)
        record(.queryBegan(token))
        return token
    }

    func endQuery(_ token: InputLifecycleQueryToken?, value: Bool) {
        guard let token else { return }
        record(.queryReturned(token, value))
    }

    func record(_ event: InputLifecycleEvent) {
        guard let record = budget.record(event, uptimeNanoseconds: DispatchTime.now().uptimeNanoseconds) else { return }
        let fields = record.event.fields
        logger.notice("schema=\(record.schemaVersion, privacy: .public) sequence=\(record.sequence, privacy: .public) uptime_ns=\(record.uptimeNanoseconds, privacy: .public) event=\(fields.event, privacy: .public) name=\(fields.name, privacy: .public) token=\(fields.token, privacy: .public) tap=\(fields.tap, privacy: .public) result=\(fields.result, privacy: .public) reason=\(fields.reason, privacy: .public) generation=\(fields.generation, privacy: .public)")
    }
}
