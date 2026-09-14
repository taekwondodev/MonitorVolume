import ApplicationServices
@preconcurrency import CoreGraphics
import Foundation
import MonitorVolumeCore

private final class MediaKeyDeliverySignal: Sendable {
    let stream: AsyncStream<Void>
    private let continuation: AsyncStream<Void>.Continuation

    init() {
        let pair = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
        stream = pair.stream
        continuation = pair.continuation
    }

    func signal() {
        continuation.yield()
    }

    func finish() {
        continuation.finish()
    }
}

@MainActor
protocol MediaKeyInterceptorDelegate: AnyObject {
    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, received delivery: AdmittedMediaKey)
    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, requestedSuspension reason: InputSuspensionReason)
    func mediaKeyInterceptorDidReleaseTap(_ interceptor: MediaKeyInterceptor)
}

@MainActor
final class MediaKeyInterceptor {
    weak var delegate: (any MediaKeyInterceptorDelegate)?

    private let eligibility: ControlEligibility
    private let diagnostics: InputLifecycleDiagnostics?
    private var diagnosticTap: UInt64 = 0
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var isDeinitializing = false
    private let deliverySignal: MediaKeyDeliverySignal
    private var deliveryConsumer: Task<Void, Never>?
    private var suspensionNotification: Task<Void, Never>?

    var hasAccessibility: Bool {
        let query = diagnostics?.beginQuery(.accessibility, tap: diagnosticTap)
        let trusted = AXIsProcessTrustedWithOptions(nil)
        diagnostics?.endQuery(query, value: trusted)
        return trusted
    }

    init(eligibility: ControlEligibility, diagnostics: InputLifecycleDiagnostics?) {
        self.eligibility = eligibility
        self.diagnostics = diagnostics
        let deliverySignal = MediaKeyDeliverySignal()
        self.deliverySignal = deliverySignal
        deliveryConsumer = nil
        deliveryConsumer = Task { @MainActor [weak self, deliverySignal] in
            for await _ in deliverySignal.stream {
                guard !Task.isCancelled else { return }
                self?.consumeDeliveries()
            }
        }
    }

    isolated deinit {
        isDeinitializing = true
        deliveryConsumer?.cancel()
        deliverySignal.finish()
        suspensionNotification?.cancel()
        stop(reason: .deinitialization)
    }

    func open(generation: UInt64, permissionFailure: InputSuspensionReason) -> Bool {
        guard eligibility.generation == generation,
              eligibility.phase.isLifecycleActive else {
            return false
        }
        guard hasAccessibility else {
            suspend(permissionFailure)
            return false
        }
        if eventTap != nil {
            guard eligibility.snapshot.tapOwnerActive else {
                suspend(.tapCreationFailed)
                return false
            }
            return true
        }
        return start(generation: generation)
    }

    func validateActive(generation: UInt64) -> Bool {
        guard eligibility.generation == generation,
              eligibility.phase.isLifecycleActive else {
            return false
        }
        guard eligibility.snapshot.tapOwnerActive else {
            suspend(.tapCreationFailed)
            return false
        }
        guard hasAccessibility else {
            suspend(.permissionRevoked)
            return false
        }
        guard let eventTap else {
            suspend(.tapCreationFailed)
            return false
        }
        let query = diagnostics?.beginQuery(.tapEnabled, tap: diagnosticTap)
        let enabled = CGEvent.tapIsEnabled(tap: eventTap)
        diagnostics?.endQuery(query, value: enabled)
        guard enabled else {
            suspend(.tapDisabledByUserInput)
            return false
        }
        return true
    }

    func requestPermissions() {
        if !hasAccessibility {
            let operation = diagnostics?.begin(.permissionPrompt, tap: diagnosticTap, reason: .reopen)
            _ = AXIsProcessTrustedWithOptions(["AXTrustedCheckOptionPrompt": true] as CFDictionary)
            diagnostics?.end(operation)
        }
    }

    func stop(reason: InputLifecycleReason) {
        let ownerWasActive = eligibility.snapshot.tapOwnerActive
        let operation = (runLoopSource != nil || eventTap != nil)
            ? diagnostics?.begin(.stop, tap: diagnosticTap, reason: reason)
            : nil
        if let runLoopSource {
            let removal = diagnostics?.begin(.sourceRemove, tap: diagnosticTap, reason: reason)
            CFRunLoopRemoveSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
            diagnostics?.end(removal)
        }
        if let eventTap {
            let invalidation = diagnostics?.begin(.tapInvalidate, tap: diagnosticTap, reason: reason)
            CFMachPortInvalidate(eventTap)
            diagnostics?.end(invalidation)
        }
        runLoopSource = nil
        eventTap = nil
        eligibility.releaseTap()
        diagnostics?.end(operation)
        diagnosticTap = 0
        if ownerWasActive, !isDeinitializing {
            delegate?.mediaKeyInterceptorDidReleaseTap(self)
        }
    }

    fileprivate func handleCallback(type: CGEventType, event: CGEvent) -> Bool {
        diagnostics?.record(.callbackEntered)
        defer { diagnostics?.record(.callbackExited) }

        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            let reason: InputSuspensionReason = type == .tapDisabledByTimeout
                ? .tapDisabledByTimeout
                : .tapDisabledByUserInput
            diagnostics?.record(.tapDisabled(type == .tapDisabledByTimeout ? .timeout : .userInput, tap: diagnosticTap))
            suspend(reason)
            return true
        }

        guard let parsed = MediaKeyEventParser.parse(event) else {
            diagnostics?.record(.handoff(.passedThrough, generation: eligibility.generation, deliverySequence: 0))
            return true
        }
        switch eligibility.route(parsed) {
        case .passThrough:
            diagnostics?.record(.handoff(.passedThrough, generation: eligibility.generation, deliverySequence: 0))
            return true
        case let .consumeKeyDown(delivery):
            diagnostics?.record(.handoff(
                .admitted,
                generation: delivery.session.generation,
                deliverySequence: delivery.sequence
            ))
            deliverySignal.signal()
            return false
        case .consumeKeyUp:
            diagnostics?.record(.handoff(.pairedKeyUp, generation: eligibility.generation, deliverySequence: 0))
            return false
        }
    }

    private func start(generation: UInt64) -> Bool {
        guard eventTap == nil else {
            return eligibility.snapshot.tapOwnerActive
        }
        let systemDefinedEventMask = CGEventMask(1) << 14
        let creation = diagnostics?.begin(.tapCreate, reason: .tapUnavailable)
        diagnosticTap = creation?.sequence ?? 0
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: systemDefinedEventMask,
            callback: mediaKeyEventTapCallback,
            userInfo: Unmanaged.passUnretained(self).toOpaque()
        ) else {
            diagnostics?.end(creation, result: .failed)
            suspend(.tapCreationFailed)
            return false
        }
        diagnostics?.end(creation)
        let sourceCreation = diagnostics?.begin(.sourceCreate, tap: diagnosticTap, reason: .tapUnavailable)
        guard let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0) else {
            diagnostics?.end(sourceCreation, result: .failed)
            CFMachPortInvalidate(tap)
            suspend(.tapCreationFailed)
            return false
        }
        diagnostics?.end(sourceCreation)
        guard eligibility.claimTapOwner(generation: generation) else {
            CFMachPortInvalidate(tap)
            return false
        }
        eventTap = tap
        runLoopSource = source
        let addition = diagnostics?.begin(.sourceAdd, tap: diagnosticTap, reason: .tapUnavailable)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        diagnostics?.end(addition)
        let enabling = diagnostics?.begin(.tapEnable, tap: diagnosticTap, reason: .tapUnavailable)
        CGEvent.tapEnable(tap: tap, enable: true)
        diagnostics?.end(enabling)
        return true
    }

    private func consumeDeliveries() {
        while let delivery = eligibility.dequeue() {
            guard eligibility.contains(delivery.session) else {
                diagnostics?.record(.handoff(
                    .staleDiscarded,
                    generation: eligibility.generation,
                    deliverySequence: delivery.sequence
                ))
                continue
            }
            delegate?.mediaKeyInterceptor(self, received: delivery)
        }
    }

    private func suspend(_ reason: InputSuspensionReason) {
        let generation = eligibility.suspend(reason)
        scheduleSuspensionNotification(reason, generation: generation)
    }

    private func scheduleSuspensionNotification(_ reason: InputSuspensionReason, generation: UInt64) {
        guard suspensionNotification == nil else { return }
        suspensionNotification = Task { @MainActor [weak self] in
            guard let self else { return }
            suspensionNotification = nil
            guard self.eligibility.generation == generation,
                  self.eligibility.phase.isSuspended else { return }
            delegate?.mediaKeyInterceptor(self, requestedSuspension: reason)
        }
    }
}

private func mediaKeyEventTapCallback(
    proxy: CGEventTapProxy,
    type: CGEventType,
    event: CGEvent,
    userInfo: UnsafeMutableRawPointer?
) -> Unmanaged<CGEvent>? {
    guard let userInfo else {
        return Unmanaged.passUnretained(event)
    }
    let interceptor = Unmanaged<MediaKeyInterceptor>.fromOpaque(userInfo).takeUnretainedValue()
    let shouldPass = MainActor.assumeIsolated {
        interceptor.handleCallback(type: type, event: event)
    }
    return shouldPass ? Unmanaged.passUnretained(event) : nil
}
