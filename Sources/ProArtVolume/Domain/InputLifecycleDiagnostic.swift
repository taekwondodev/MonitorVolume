enum InputLifecycleConfiguration: Equatable {
    case disabled
    case enabled
    case duplicateFlag

    init(arguments: [String]) {
        switch arguments.filter({ $0 == "--diagnose-input-lifecycle" }).count {
        case 0: self = .disabled
        case 1: self = .enabled
        default: self = .duplicateFlag
        }
    }
}

enum InputLifecycleReason: String, Sendable {
    case launch, reopen, permissionPoll, outputChanged, displayChanged
    case sleep, wake, termination, deinitialization, tapUnavailable
    case missingAccessibility, permissionRevoked, disabledTap, deliveryOverflow, creationFailure
}

enum InputLifecycleOperation: String, Sendable {
    case permissionPoll, stop, tapCreate, sourceCreate, sourceAdd, tapEnable
    case sourceRemove, tapInvalidate, permissionPrompt
}

enum InputLifecycleQuery: String, Sendable {
    case accessibility, tapEnabled
}

struct InputLifecycleOperationToken: Equatable, Sendable {
    let sequence: UInt64
    let kind: InputLifecycleOperation
    let tap: UInt64
}

struct InputLifecycleQueryToken: Equatable, Sendable {
    let sequence: UInt64
    let kind: InputLifecycleQuery
    let tap: UInt64
}

enum InputLifecycleOperationResult: String, Sendable {
    case returned, failed
}

enum InputLifecycleRevalidation: String, Sendable {
    case requested, entered, staleDiscarded, serviceScheduled
}

enum InputLifecycleSkip: String, Sendable {
    case sleeping, stopped
}

enum InputLifecycleDisableReason: String, Sendable {
    case timeout, userInput
}

enum InputLifecycleHandoff: String, Sendable {
    case admitted
    case pairedKeyUp
    case passedThrough
    case overflow
    case staleDiscarded
}

enum InputLifecycleEvent: Equatable, Sendable {
    case sessionStarted
    case sessionEnded
    case budgetExhausted
    case lifecycle(InputLifecycleReason, generation: UInt64)
    case revalidation(InputLifecycleRevalidation, InputLifecycleReason, generation: UInt64)
    case pollSkipped(InputLifecycleSkip)
    case tapDisabled(InputLifecycleDisableReason, tap: UInt64)
    case callbackEntered
    case callbackExited
    case handoff(InputLifecycleHandoff, generation: UInt64, deliverySequence: UInt64)
    case operationBegan(InputLifecycleOperationToken, InputLifecycleReason)
    case operationEnded(InputLifecycleOperationToken, InputLifecycleOperationResult)
    case queryBegan(InputLifecycleQueryToken)
    case queryReturned(InputLifecycleQueryToken, Bool)

    var fields: InputLifecycleFields {
        switch self {
        case .sessionStarted: .init(event: "sessionStarted")
        case .sessionEnded: .init(event: "sessionEnded")
        case .budgetExhausted: .init(event: "budgetExhausted")
        case let .lifecycle(reason, generation):
            .init(event: "lifecycle", reason: reason.rawValue, generation: generation)
        case let .revalidation(phase, reason, generation):
            .init(event: "revalidation", name: phase.rawValue, reason: reason.rawValue, generation: generation)
        case let .pollSkipped(reason):
            .init(event: "pollSkipped", reason: reason.rawValue)
        case let .tapDisabled(reason, tap):
            .init(event: "tapDisabled", tap: tap, reason: reason.rawValue)
        case .callbackEntered:
            .init(event: "callbackEntered")
        case .callbackExited:
            .init(event: "callbackExited")
        case let .handoff(result, generation, deliverySequence):
            .init(event: "handoff", name: result.rawValue, token: deliverySequence, generation: generation)
        case let .operationBegan(token, reason):
            .init(event: "operationBegan", name: token.kind.rawValue, token: token.sequence,
                  tap: token.tap, reason: reason.rawValue)
        case let .operationEnded(token, result):
            .init(event: "operationEnded", name: token.kind.rawValue, token: token.sequence,
                  tap: token.tap, result: result.rawValue)
        case let .queryBegan(token):
            .init(event: "queryBegan", name: token.kind.rawValue, token: token.sequence, tap: token.tap)
        case let .queryReturned(token, value):
            .init(event: "queryReturned", name: token.kind.rawValue, token: token.sequence,
                  tap: token.tap, result: value ? "true" : "false")
        }
    }
}

struct InputLifecycleFields: Equatable, Sendable {
    let event: String
    var name: String = "none"
    var token: UInt64 = 0
    var tap: UInt64 = 0
    var result: String = "none"
    var reason: String = "none"
    var generation: UInt64 = 0
}

struct InputLifecycleRecord: Equatable, Sendable {
    let schemaVersion = 1
    let sequence: UInt64
    let uptimeNanoseconds: UInt64
    let event: InputLifecycleEvent
}

struct InputLifecycleBudget {
    static let regularRecordLimit: UInt64 = 2_048
    private(set) var sequence: UInt64 = 0
    private var ended = false

    var acceptsRegularRecord: Bool { !ended && sequence < Self.regularRecordLimit }

    mutating func record(_ event: InputLifecycleEvent, uptimeNanoseconds: UInt64) -> InputLifecycleRecord? {
        guard !ended, sequence <= Self.regularRecordLimit else { return nil }
        let emitted = acceptsRegularRecord ? event : .budgetExhausted
        sequence += 1
        ended = emitted == .sessionEnded || emitted == .budgetExhausted
        return InputLifecycleRecord(sequence: sequence, uptimeNanoseconds: uptimeNanoseconds, event: emitted)
    }
}
