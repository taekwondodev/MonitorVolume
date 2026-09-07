import ApplicationServices
@preconcurrency import CoreGraphics
import Foundation
import ProArtVolumeCore

@MainActor
protocol MediaKeyInterceptorDelegate: AnyObject {
    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, received command: MediaKeyCommand, session: ControlSession)
    func mediaKeyInterceptorBecameUnavailable(_ interceptor: MediaKeyInterceptor)
}

@MainActor
final class MediaKeyInterceptor {
    weak var delegate: (any MediaKeyInterceptorDelegate)?

    private let eligibility: ControlEligibility
    private let diagnostics: InputLifecycleDiagnostics?
    private var diagnosticTap: UInt64 = 0
    private var routing = MediaKeyRouting()
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?

    var hasAccessibility: Bool {
        let query = diagnostics?.beginQuery(.accessibility, tap: diagnosticTap)
        let trusted = AXIsProcessTrustedWithOptions(nil)
        diagnostics?.endQuery(query, value: trusted)
        return trusted
    }

    init(eligibility: ControlEligibility, diagnostics: InputLifecycleDiagnostics?) {
        self.eligibility = eligibility
        self.diagnostics = diagnostics
    }

    func refreshPermissions() -> Bool {
        guard hasAccessibility else {
            stop(reason: .missingAccessibility)
            return false
        }
        if let eventTap {
            let query = diagnostics?.beginQuery(.tapEnabled, tap: diagnosticTap)
            let enabled = CGEvent.tapIsEnabled(tap: eventTap)
            diagnostics?.endQuery(query, value: enabled)
            if !enabled { stop(reason: .disabledTap) }
        }
        start()
        return eventTap != nil
    }

    func requestPermissions() {
        if !hasAccessibility {
            let operation = diagnostics?.begin(.permissionPrompt, tap: diagnosticTap, reason: .reopen)
            _ = AXIsProcessTrustedWithOptions(["AXTrustedCheckOptionPrompt": true] as CFDictionary)
            diagnostics?.end(operation)
        }
    }

    func stop(reason: InputLifecycleReason) {
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
        routing = MediaKeyRouting()
        diagnostics?.end(operation)
        diagnosticTap = 0
    }

    fileprivate func shouldPass(type: CGEventType, event: CGEvent) -> Bool {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            diagnostics?.record(.tapDisabled(type == .tapDisabledByTimeout ? .timeout : .userInput, tap: diagnosticTap))
            mediaKeyUnavailable()
            return true
        }
        let parsed = MediaKeyEventParser.parse(event)
        let session = eligibility.session
        switch routing.decision(for: parsed, targetIsActive: session != nil) {
        case .passThrough:
            return true
        case let .consumeKeyDown(command):
            guard let session else { return true }
            delegate?.mediaKeyInterceptor(self, received: command, session: session)
            return false
        case .consumeKeyUp:
            return false
        }
    }

    private func start() {
        guard eventTap == nil else {
            return
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
            stop(reason: .creationFailure)
            return
        }
        diagnostics?.end(creation)
        let sourceCreation = diagnostics?.begin(.sourceCreate, tap: diagnosticTap, reason: .tapUnavailable)
        guard let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0) else {
            diagnostics?.end(sourceCreation, result: .failed)
            stop(reason: .creationFailure)
            return
        }
        diagnostics?.end(sourceCreation)
        eventTap = tap
        runLoopSource = source
        let addition = diagnostics?.begin(.sourceAdd, tap: diagnosticTap, reason: .tapUnavailable)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        diagnostics?.end(addition)
        let enabling = diagnostics?.begin(.tapEnable, tap: diagnosticTap, reason: .tapUnavailable)
        CGEvent.tapEnable(tap: tap, enable: true)
        diagnostics?.end(enabling)
    }

    private func mediaKeyUnavailable() {
        delegate?.mediaKeyInterceptorBecameUnavailable(self)
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
        interceptor.shouldPass(type: type, event: event)
    }
    return shouldPass ? Unmanaged.passUnretained(event) : nil
}
