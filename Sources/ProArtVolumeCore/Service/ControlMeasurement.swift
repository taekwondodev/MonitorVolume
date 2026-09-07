package struct ControlMeasurementID: Hashable, Sendable {
    package let rawValue: UInt64

    package init(_ rawValue: UInt64) {
        self.rawValue = rawValue
    }
}

package struct ControlMeasurementContext: Sendable {
    package let interactionIDs: [ControlMeasurementID]

    package init(interactionIDs: [ControlMeasurementID]) {
        self.interactionIDs = interactionIDs
    }
}

package enum ControlMeasurementStage: Sendable {
    case commandEnqueued
    case commandStarted
    case commandCompleted
    case commandSuperseded
    case commandDiscarded
}

package struct ControlMeasurementObserver: Sendable {
    private let recordBody: @Sendable (ControlMeasurementStage, ControlMeasurementContext) -> Void

    package init(
        record: @escaping @Sendable (ControlMeasurementStage, ControlMeasurementContext) -> Void
    ) {
        recordBody = record
    }

    package func record(_ stage: ControlMeasurementStage, context: ControlMeasurementContext) {
        recordBody(stage, context)
    }
}

package enum ControlMeasurementTaskContext {
    @TaskLocal package static var current: ControlMeasurementContext?
}
