import Dispatch
import Synchronization

package struct ControlSession: Equatable, Sendable {
    package let generation: UInt64
    package let seedRevision: UInt64
    package let seed: ConfirmedMonitorState

    package init(generation: UInt64, seedRevision: UInt64, seed: ConfirmedMonitorState) {
        self.generation = generation
        self.seedRevision = seedRevision
        self.seed = seed
    }
}

package enum InputSuspensionReason: Equatable, Sendable {
    case missingPermission
    case permissionRevoked
    case tapDisabledByTimeout
    case tapDisabledByUserInput
    case deliveryOverflow
    case tapCreationFailed
}

package enum ControlEligibilityPhase: Equatable, Sendable {
    case unavailable
    case validating
    case activeWithoutHardware
    case eligible(ControlSession)
    case suspended(InputSuspensionReason)
    case sleepingAfterActive
    case sleepingWhileSuspended(InputSuspensionReason)
    case sleepingWhileUnavailable

    package var isSuspended: Bool {
        switch self {
        case .suspended, .sleepingWhileSuspended:
            true
        case .unavailable, .validating, .activeWithoutHardware, .eligible, .sleepingAfterActive, .sleepingWhileUnavailable:
            false
        }
    }

    package var isLifecycleActive: Bool {
        switch self {
        case .validating, .activeWithoutHardware, .eligible:
            true
        case .unavailable, .suspended, .sleepingAfterActive, .sleepingWhileSuspended, .sleepingWhileUnavailable:
            false
        }
    }
}

package struct InputAdmissionMetrics: Equatable, Sendable {
    package let attemptedCount: UInt64
    package let admittedCount: UInt64
    package let rejectedCount: UInt64
    package let discardedCount: UInt64
    package let overflowCount: UInt64
    package let completedCount: UInt64
    package let peakOutstanding: Int
    package let maximumDeliveryWaitNanoseconds: UInt64
}

package struct ControlEligibilitySnapshot: Equatable, Sendable {
    package let generation: UInt64
    package let phase: ControlEligibilityPhase
    package let session: ControlSession?
    package let tapOwnerActive: Bool
    package let capacity: Int
    package let pendingDeliveryCount: Int
    package let metrics: InputAdmissionMetrics
}

package struct AdmittedMediaKey: Equatable, Sendable {
    package let sequence: UInt64
    package let acceptedAtNanoseconds: UInt64
    package let command: MediaKeyCommand
    package let session: ControlSession
}

package enum InputAdmissionDecision: Equatable, Sendable {
    case passThrough
    case consumeKeyDown(AdmittedMediaKey)
    case consumeKeyUp
    case passThroughAfterOverflow
}

package enum WakeResult: Equatable, Sendable {
    case revalidate(generation: UInt64)
    case waitingForTapRelease
    case remainsSuspended(InputSuspensionReason)
    case remainsUnavailable(generation: UInt64)
    case ignored
}

package enum ReopenResult: Equatable, Sendable {
    case started(generation: UInt64)
    case waitingForTapRelease
}

package final class ControlEligibility: Sendable {
    private struct State: Sendable {
        var generation: UInt64 = 0
        var phase: ControlEligibilityPhase = .unavailable
        var tapOwnerActive = false
        let capacity: Int
        var nextDeliverySequence: UInt64 = 0
        var queued: [AdmittedMediaKey] = []
        var inFlight: [UInt64: AdmittedMediaKey] = [:]
        var consumedKeyDowns: Set<MediaKey> = []
        var attemptedCount: UInt64 = 0
        var admittedCount: UInt64 = 0
        var rejectedCount: UInt64 = 0
        var discardedCount: UInt64 = 0
        var overflowCount: UInt64 = 0
        var completedCount: UInt64 = 0
        var peakOutstanding = 0
        var maximumDeliveryWaitNanoseconds: UInt64 = 0

        init(capacity: Int) {
            self.capacity = capacity
        }

        var metrics: InputAdmissionMetrics {
            InputAdmissionMetrics(
                attemptedCount: attemptedCount,
                admittedCount: admittedCount,
                rejectedCount: rejectedCount,
                discardedCount: discardedCount,
                overflowCount: overflowCount,
                completedCount: completedCount,
                peakOutstanding: peakOutstanding,
                maximumDeliveryWaitNanoseconds: maximumDeliveryWaitNanoseconds
            )
        }
    }

    private let state: Mutex<State>

    package init(capacity: Int = 8) {
        precondition(capacity > 0)
        state = Mutex(State(capacity: capacity))
    }

    package var generation: UInt64 { state.withLock { $0.generation } }

    package var session: ControlSession? {
        state.withLock { state in
            guard case let .eligible(session) = state.phase else { return nil }
            return session
        }
    }

    package var phase: ControlEligibilityPhase { state.withLock { $0.phase } }

    package var allowsPermissionPolling: Bool {
        state.withLock { $0.phase.isLifecycleActive }
    }

    package var pendingDeliveryCount: Int {
        state.withLock { $0.queued.count + $0.inFlight.count }
    }

    package var snapshot: ControlEligibilitySnapshot {
        state.withLock { state in
            let session: ControlSession? = if case let .eligible(session) = state.phase { session } else { nil }
            return ControlEligibilitySnapshot(
                generation: state.generation,
                phase: state.phase,
                session: session,
                tapOwnerActive: state.tapOwnerActive,
                capacity: state.capacity,
                pendingDeliveryCount: state.queued.count + state.inFlight.count,
                metrics: state.metrics
            )
        }
    }

    @discardableResult
    package func invalidate() -> UInt64 {
        state.withLock { state in
            state.generation &+= 1
            switch state.phase {
            case let .suspended(reason):
                state.phase = .suspended(reason)
            case let .sleepingWhileSuspended(reason):
                state.phase = .sleepingWhileSuspended(reason)
            case .sleepingAfterActive:
                state.phase = .sleepingAfterActive
            case .sleepingWhileUnavailable:
                state.phase = .sleepingWhileUnavailable
            case .unavailable, .validating, .activeWithoutHardware, .eligible:
                state.phase = .unavailable
            }
            discardQueued(&state)
            return state.generation
        }
    }

    @discardableResult
    package func reopen() -> ReopenResult {
        state.withLock { state in
            guard !state.tapOwnerActive else { return .waitingForTapRelease }
            state.generation &+= 1
            state.phase = .validating
            discardQueued(&state)
            return .started(generation: state.generation)
        }
    }

    package func beginValidation(generation: UInt64) -> Bool {
        state.withLock { state in
            guard state.generation == generation, !state.phase.isSuspended else { return false }
            guard state.phase != .sleepingAfterActive,
                  state.phase != .sleepingWhileUnavailable else { return false }
            state.phase = .validating
            discardQueued(&state)
            return true
        }
    }

    package func markUnavailable(generation: UInt64) {
        state.withLock { state in
            guard state.generation == generation, !state.phase.isSuspended else { return }
            switch state.phase {
            case .unavailable, .suspended, .sleepingAfterActive, .sleepingWhileSuspended, .sleepingWhileUnavailable:
                return
            case .validating, .activeWithoutHardware, .eligible:
                state.phase = .activeWithoutHardware
            }
            discardQueued(&state)
        }
    }

    @discardableResult
    package func suspend(_ reason: InputSuspensionReason) -> UInt64 {
        state.withLock { state in
            state.generation &+= 1
            state.phase = .suspended(reason)
            discardQueued(&state)
            return state.generation
        }
    }

    package func publish(_ session: ControlSession) {
        state.withLock { state in
            guard state.generation == session.generation else { return }
            guard state.phase == .validating || state.phase == .activeWithoutHardware else { return }
            state.phase = .eligible(session)
        }
    }

    package func claimTapOwner(generation: UInt64) -> Bool {
        state.withLock { state in
            guard state.generation == generation,
                  state.phase.isLifecycleActive else { return false }
            state.tapOwnerActive = true
            return true
        }
    }

    package func contains(_ session: ControlSession) -> Bool {
        state.withLock { $0.phase == .eligible(session) }
    }

    package func route(
        _ event: MediaKeyEvent,
        at uptimeNanoseconds: UInt64 = DispatchTime.now().uptimeNanoseconds
    ) -> InputAdmissionDecision {
        state.withLock { state in
            switch event.phase {
            case .down:
                state.attemptedCount &+= 1
                guard state.tapOwnerActive else {
                    state.rejectedCount &+= 1
                    return .passThrough
                }
                guard case let .eligible(session) = state.phase else {
                    state.rejectedCount &+= 1
                    return .passThrough
                }
                guard state.queued.count + state.inFlight.count < state.capacity else {
                    state.rejectedCount &+= 1
                    state.overflowCount &+= 1
                    state.generation &+= 1
                    state.phase = .suspended(.deliveryOverflow)
                    discardQueued(&state)
                    return .passThroughAfterOverflow
                }
                state.nextDeliverySequence &+= 1
                let delivery = AdmittedMediaKey(
                    sequence: state.nextDeliverySequence,
                    acceptedAtNanoseconds: uptimeNanoseconds,
                    command: event.key.command,
                    session: session
                )
                state.queued.append(delivery)
                state.consumedKeyDowns.insert(event.key)
                state.admittedCount &+= 1
                state.peakOutstanding = max(state.peakOutstanding, state.queued.count + state.inFlight.count)
                return .consumeKeyDown(delivery)
            case .up:
                guard state.consumedKeyDowns.remove(event.key) != nil else {
                    state.rejectedCount &+= 1
                    return .passThrough
                }
                return .consumeKeyUp
            }
        }
    }

    package func dequeue(
        at uptimeNanoseconds: UInt64 = DispatchTime.now().uptimeNanoseconds
    ) -> AdmittedMediaKey? {
        state.withLock { state in
            guard !state.queued.isEmpty else { return nil }
            let delivery = state.queued.removeFirst()
            state.inFlight[delivery.sequence] = delivery
            let wait = uptimeNanoseconds &- delivery.acceptedAtNanoseconds
            state.maximumDeliveryWaitNanoseconds = max(state.maximumDeliveryWaitNanoseconds, wait)
            return delivery
        }
    }

    @discardableResult
    package func complete(_ delivery: AdmittedMediaKey) -> Bool {
        state.withLock { state in
            guard state.inFlight.removeValue(forKey: delivery.sequence) != nil else { return false }
            state.completedCount &+= 1
            return true
        }
    }

    package func discardPending() {
        state.withLock { discardQueued(&$0) }
    }

    package func releaseTap() {
        state.withLock { state in
            discardQueued(&state)
            state.consumedKeyDowns.removeAll(keepingCapacity: false)
            state.tapOwnerActive = false
        }
    }

    package func sleep() -> UInt64 {
        state.withLock { state in
            state.generation &+= 1
            switch state.phase {
            case .eligible, .validating, .activeWithoutHardware:
                state.phase = .sleepingAfterActive
            case let .suspended(reason):
                state.phase = .sleepingWhileSuspended(reason)
            case .sleepingAfterActive:
                state.phase = .sleepingAfterActive
            case let .sleepingWhileSuspended(reason):
                state.phase = .sleepingWhileSuspended(reason)
            case .sleepingWhileUnavailable:
                state.phase = .sleepingWhileUnavailable
            case .unavailable:
                state.phase = .sleepingWhileUnavailable
            }
            discardQueued(&state)
            return state.generation
        }
    }

    package func wake() -> WakeResult {
        state.withLock { state in
            switch state.phase {
            case .sleepingAfterActive:
                guard !state.tapOwnerActive else { return .waitingForTapRelease }
                state.generation &+= 1
                state.phase = .validating
                return .revalidate(generation: state.generation)
            case let .sleepingWhileSuspended(reason):
                guard !state.tapOwnerActive else { return .waitingForTapRelease }
                state.generation &+= 1
                state.phase = .suspended(reason)
                return .remainsSuspended(reason)
            case .sleepingWhileUnavailable:
                guard !state.tapOwnerActive else { return .waitingForTapRelease }
                state.generation &+= 1
                state.phase = .activeWithoutHardware
                return .remainsUnavailable(generation: state.generation)
            case .unavailable, .validating, .activeWithoutHardware, .eligible, .suspended:
                return .ignored
            }
        }
    }

    private func discardQueued(_ state: inout State) {
        state.discardedCount &+= UInt64(state.queued.count)
        state.queued.removeAll(keepingCapacity: true)
    }
}
