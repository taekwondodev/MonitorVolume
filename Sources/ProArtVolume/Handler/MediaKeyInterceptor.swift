import ApplicationServices
@preconcurrency import CoreGraphics
import Foundation
import ProArtVolumeCore

enum MediaKeyPermissionState: Equatable {
    case granted
    case missingInputMonitoring
    case missingAccessibility
    case missingInputMonitoringAndAccessibility

    var explanation: String? {
        switch self {
        case .granted:
            nil
        case .missingInputMonitoring:
            "Input Monitoring is required to see the three volume media keys."
        case .missingAccessibility:
            "Accessibility is required to intercept the three volume media keys."
        case .missingInputMonitoringAndAccessibility:
            "Input Monitoring and Accessibility are required only to intercept the three volume media keys."
        }
    }
}

@MainActor
protocol MediaKeyInterceptorDelegate: AnyObject {
    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, received command: MediaKeyCommand)
}

@MainActor
final class MediaKeyInterceptor {
    weak var delegate: (any MediaKeyInterceptorDelegate)?

    private let routingSnapshot: MediaKeyRoutingSnapshot
    private var routing = MediaKeyRouting()
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?

    private(set) var permissionState: MediaKeyPermissionState = .missingInputMonitoringAndAccessibility

    init(routingSnapshot: MediaKeyRoutingSnapshot) {
        self.routingSnapshot = routingSnapshot
    }

    func refreshPermissions() {
        let accessibility = AXIsProcessTrustedWithOptions(nil)
        if accessibility {
            start()
            if eventTap != nil {
                permissionState = .granted
                return
            }
            permissionState = .missingInputMonitoring
            stop()
            return
        }

        let inputMonitoring = CGPreflightListenEventAccess()
        permissionState = Self.permissionState(
            inputMonitoring: inputMonitoring,
            accessibility: accessibility
        )
        stop()
    }

    func requestPermissions() {
        if !AXIsProcessTrustedWithOptions(nil) {
            _ = AXIsProcessTrustedWithOptions(["AXTrustedCheckOptionPrompt": true] as CFDictionary)
        } else if eventTap == nil, !CGPreflightListenEventAccess() {
            CGRequestListenEventAccess()
        }
        refreshPermissions()
    }

    func stop() {
        if let runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        }
        if let eventTap {
            CFMachPortInvalidate(eventTap)
        }
        runLoopSource = nil
        eventTap = nil
        routing = MediaKeyRouting()
    }

    fileprivate func shouldPass(type: CGEventType, event: CGEvent) -> Bool {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let eventTap {
                CGEvent.tapEnable(tap: eventTap, enable: true)
            }
            return true
        }
        let parsed = MediaKeyEventParser.parse(event)
        switch routing.decision(for: parsed, targetIsActive: routingSnapshot.read()) {
        case .passThrough:
            return true
        case let .consumeKeyDown(command):
            delegate?.mediaKeyInterceptor(self, received: command)
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
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: systemDefinedEventMask,
            callback: mediaKeyEventTapCallback,
            userInfo: Unmanaged.passUnretained(self).toOpaque()
        ), let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0) else {
            stop()
            return
        }
        eventTap = tap
        runLoopSource = source
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
    }

    private static func permissionState(
        inputMonitoring: Bool,
        accessibility: Bool
    ) -> MediaKeyPermissionState {
        switch (inputMonitoring, accessibility) {
        case (true, true):
            .granted
        case (false, true):
            .missingInputMonitoring
        case (true, false):
            .missingAccessibility
        case (false, false):
            .missingInputMonitoringAndAccessibility
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
        interceptor.shouldPass(type: type, event: event)
    }
    return shouldPass ? Unmanaged.passUnretained(event) : nil
}
