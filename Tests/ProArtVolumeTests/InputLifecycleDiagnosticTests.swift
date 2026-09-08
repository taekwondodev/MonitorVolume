import Testing
@testable import ProArtVolume

struct InputLifecycleDiagnosticTests {
    @Test func configurationRequiresExplicitProcessFlag() {
        #expect(InputLifecycleConfiguration(arguments: ["app"]) == .disabled)
        #expect(InputLifecycleConfiguration(arguments: ["app", "--latency-evidence", "/fixture.json"]) == .disabled)
        #expect(InputLifecycleConfiguration(arguments: ["app", "--diagnose-input-lifecycle"]) == .enabled)
        #expect(InputLifecycleConfiguration(arguments: ["app", "--diagnose-input-lifecycle",
                                                       "--diagnose-input-lifecycle"]) == .duplicateFlag)
        #expect(InputLifecycleConfiguration(arguments: ["app", "--diagnose-input-lifecycle=false"]) == .disabled)
    }

    @Test func fixedFieldsPreserveFalseQueryAndOperationIdentity() {
        let query = InputLifecycleQueryToken(sequence: 2, kind: .accessibility, tap: 7)
        #expect(InputLifecycleEvent.queryReturned(query, false).fields == InputLifecycleFields(
            event: "queryReturned", name: "accessibility", token: 2, tap: 7, result: "false"))
        let operation = InputLifecycleOperationToken(sequence: 4, kind: .tapInvalidate, tap: 7)
        #expect(InputLifecycleEvent.operationBegan(operation, .missingAccessibility).fields == InputLifecycleFields(
            event: "operationBegan", name: "tapInvalidate", token: 4, tap: 7, reason: "missingAccessibility"))
        #expect(InputLifecycleEvent.operationEnded(operation, .returned).fields == InputLifecycleFields(
            event: "operationEnded", name: "tapInvalidate", token: 4, tap: 7, result: "returned"))
        #expect(InputLifecycleEvent.tapDisabled(.userInput, tap: 7).fields == InputLifecycleFields(
            event: "tapDisabled", tap: 7, reason: "userInput"))
    }

    @Test
    func callbackAndHandoffFieldsPreserveDeliveryIdentity() {
        #expect(InputLifecycleEvent.callbackEntered.fields == InputLifecycleFields(event: "callbackEntered"))
        #expect(InputLifecycleEvent.callbackExited.fields == InputLifecycleFields(event: "callbackExited"))
        #expect(InputLifecycleEvent.handoff(.admitted, generation: 9, deliverySequence: 3).fields == InputLifecycleFields(
            event: "handoff", name: "admitted", token: 3, generation: 9))
    }


    @Test func budgetEmitsExactlyOneExhaustionMarker() throws {
        var budget = InputLifecycleBudget()
        for sequence in UInt64(1)...2_048 {
            let emitted = budget.record(.sessionStarted, uptimeNanoseconds: 100)
            let record = try #require(emitted)
            #expect(record.schemaVersion == 1)
            #expect(record.sequence == sequence)
            #expect(record.event == .sessionStarted)
        }
        #expect(!budget.acceptsRegularRecord)
        #expect(budget.record(.sessionEnded, uptimeNanoseconds: 101) == InputLifecycleRecord(
            sequence: 2_049, uptimeNanoseconds: 101, event: .budgetExhausted))
        #expect(budget.record(.sessionEnded, uptimeNanoseconds: 102) == nil)
        #expect(budget.record(.sessionStarted, uptimeNanoseconds: 103) == nil)
    }

    @Test func sessionEndSealsEmissionWithoutChangingAppLifecycle() {
        var budget = InputLifecycleBudget()
        _ = budget.record(.sessionStarted, uptimeNanoseconds: 10)
        #expect(budget.record(.sessionEnded, uptimeNanoseconds: 11)?.event == .sessionEnded)
        #expect(!budget.acceptsRegularRecord)
        #expect(budget.record(.lifecycle(.deinitialization, generation: 1), uptimeNanoseconds: 12) == nil)
    }

    @Test func pairedFixtureIsStructurallyCompleteNotRuntimeProof() {
        let query = InputLifecycleQueryToken(sequence: 2, kind: .accessibility, tap: 0)
        let stop = InputLifecycleOperationToken(sequence: 4, kind: .stop, tap: 7)
        let records: [InputLifecycleRecord] = [
            .init(sequence: 1, uptimeNanoseconds: 10, event: .sessionStarted),
            .init(sequence: 2, uptimeNanoseconds: 11, event: .queryBegan(query)),
            .init(sequence: 3, uptimeNanoseconds: 12, event: .queryReturned(query, false)),
            .init(sequence: 4, uptimeNanoseconds: 13, event: .operationBegan(stop, .missingAccessibility)),
            .init(sequence: 5, uptimeNanoseconds: 14, event: .operationEnded(stop, .returned)),
            .init(sequence: 6, uptimeNanoseconds: 15, event: .sessionEnded),
        ]
        #expect(InputLifecycleTraceAssessment.assess(records).isComplete)
        #expect(!InputLifecycleTraceAssessment.assess(Array(records.dropFirst())).isComplete)
        #expect(!InputLifecycleTraceAssessment.assess(Array(records.dropLast())).isComplete)
        #expect(!InputLifecycleTraceAssessment.assess(records.filter { $0.sequence != 3 }).isComplete)
    }

    @Test func unfinishedOperationIsNotClassifiedAsDeadlock() {
        let stop = InputLifecycleOperationToken(sequence: 2, kind: .tapInvalidate, tap: 7)
        let result = InputLifecycleTraceAssessment.assess([
            .init(sequence: 1, uptimeNanoseconds: 10, event: .sessionStarted),
            .init(sequence: 2, uptimeNanoseconds: 11, event: .operationBegan(stop, .missingAccessibility)),
        ])
        #expect(!result.isComplete)
        #expect(result.unfinishedOperations == [2])
        #expect(!result.hasGapsOrInvalidPairs)
        #expect(!result.ended)
    }

    @Test func mismatchedTapAndLostBeginRemainIncomplete() {
        let begin = InputLifecycleOperationToken(sequence: 2, kind: .sourceRemove, tap: 7)
        let wrong = InputLifecycleOperationToken(sequence: 2, kind: .sourceRemove, tap: 8)
        #expect(InputLifecycleTraceAssessment.assess([
            .init(sequence: 1, uptimeNanoseconds: 10, event: .sessionStarted),
            .init(sequence: 2, uptimeNanoseconds: 11, event: .operationBegan(begin, .missingAccessibility)),
            .init(sequence: 3, uptimeNanoseconds: 12, event: .operationEnded(wrong, .returned)),
            .init(sequence: 4, uptimeNanoseconds: 13, event: .sessionEnded),
        ]).hasGapsOrInvalidPairs)
        #expect(InputLifecycleTraceAssessment.assess([
            .init(sequence: 1, uptimeNanoseconds: 10, event: .sessionStarted),
            .init(sequence: 2, uptimeNanoseconds: 11, event: .operationEnded(begin, .returned)),
            .init(sequence: 3, uptimeNanoseconds: 12, event: .sessionEnded),
        ]).hasGapsOrInvalidPairs)
    }

    @Test func exhaustedReorderedAndEmptyFixturesAreIncomplete() {
        #expect(!InputLifecycleTraceAssessment.assess([]).isComplete)
        let exhausted = InputLifecycleTraceAssessment.assess([
            .init(sequence: 1, uptimeNanoseconds: 10, event: .sessionStarted),
            .init(sequence: 2, uptimeNanoseconds: 11, event: .budgetExhausted),
        ])
        #expect(exhausted.budgetExhausted)
        #expect(!exhausted.isComplete)
        #expect(InputLifecycleTraceAssessment.assess([
            .init(sequence: 1, uptimeNanoseconds: 10, event: .sessionStarted),
            .init(sequence: 2, uptimeNanoseconds: 9, event: .sessionEnded),
        ]).hasGapsOrInvalidPairs)
    }
}
