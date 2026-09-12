import Synchronization

package struct ControlSession: Equatable, Sendable {
    package let generation: UInt64
    package let seedRevision: UInt64
    package let target: ResolvedMonitorTarget
    package let seed: ConfirmedMonitorState

    package init(
        generation: UInt64,
        seedRevision: UInt64,
        target: ResolvedMonitorTarget,
        seed: ConfirmedMonitorState
    ) {
        self.generation = generation
        self.seedRevision = seedRevision
        self.target = target
        self.seed = seed
    }
}

package enum InputSuspensionReason: Equatable, Sendable {
    case missingPermission
    case permissionRevoked
    case tapDisabledByTimeout
    case tapDisabledByUserInput
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

package struct ControlEligibilitySnapshot: Equatable, Sendable {
    package let generation: UInt64
    package let phase: ControlEligibilityPhase
    package let session: ControlSession?
    package let tapOwnerActive: Bool
    package let pendingDeliveryCount: Int
}

package struct AdmittedMediaKey: Equatable, Sendable {
    package let sequence: UInt64
    package let command: MediaKeyCommand
    package let session: ControlSession
}

package enum InputAdmissionDecision: Equatable, Sendable {
    case passThrough
    case consumeKeyDown(AdmittedMediaKey)
    case consumeKeyUp
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
        var nextDeliverySequence: UInt64 = 0
        var queued: [AdmittedMediaKey] = []
        var consumedKeyDowns: Set<MediaKey> = []
    }

    private let state: Mutex<State>

    package init() {
        state = Mutex(State())
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

    package var awaitsPermission: Bool {
        state.withLock { state in
            switch state.phase {
            case .suspended(.missingPermission), .suspended(.permissionRevoked):
                true
            default:
                false
            }
        }
    }

    package var pendingDeliveryCount: Int {
        state.withLock { $0.queued.count }
    }

    package var snapshot: ControlEligibilitySnapshot {
        state.withLock { state in
            let session: ControlSession? = if case let .eligible(session) = state.phase { session } else { nil }
            return ControlEligibilitySnapshot(
                generation: state.generation,
                phase: state.phase,
                session: session,
                tapOwnerActive: state.tapOwnerActive,
                pendingDeliveryCount: state.queued.count
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
                state.phase = state.tapOwnerActive ? .activeWithoutHardware : .unavailable
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
            guard !state.phase.isSuspended else { return state.generation }
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

    package func route(_ event: MediaKeyEvent) -> InputAdmissionDecision {
        state.withLock { state in
            switch event.phase {
            case .down:
                guard state.tapOwnerActive, case let .eligible(session) = state.phase else {
                    return .passThrough
                }
                guard session.target.capabilities.supports(event.key.command) else {
                    return .passThrough
                }
                state.nextDeliverySequence &+= 1
                let delivery = AdmittedMediaKey(
                    sequence: state.nextDeliverySequence,
                    command: event.key.command,
                    session: session
                )
                state.queued.append(delivery)
                state.consumedKeyDowns.insert(event.key)
                return .consumeKeyDown(delivery)
            case .up:
                guard state.consumedKeyDowns.remove(event.key) != nil else { return .passThrough }
                return .consumeKeyUp
            }
        }
    }

    package func dequeue() -> AdmittedMediaKey? {
        state.withLock { state in
            state.queued.isEmpty ? nil : state.queued.removeFirst()
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
                state.phase = .unavailable
                return .remainsUnavailable(generation: state.generation)
            case .unavailable, .validating, .activeWithoutHardware, .eligible, .suspended:
                return .ignored
            }
        }
    }

    private func discardQueued(_ state: inout State) {
        state.queued.removeAll(keepingCapacity: true)
    }
}
