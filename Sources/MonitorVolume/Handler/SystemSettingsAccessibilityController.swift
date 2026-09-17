import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

struct SystemSettingsWindowIdentity: Hashable, Sendable {
    let processID: pid_t
    let windowID: CGWindowID
}

struct SystemSettingsWindowSnapshot: Equatable, Sendable {
    let identity: SystemSettingsWindowIdentity
    let frame: CGRect
}

struct SystemSettingsWindowOwnership {
    private let baseline: Set<SystemSettingsWindowIdentity>
    private(set) var ownedWindow: SystemSettingsWindowSnapshot?
    private var claimWasResolved = false

    init(baseline: Set<SystemSettingsWindowIdentity>) {
        self.baseline = baseline
    }

    mutating func refresh(current: [SystemSettingsWindowSnapshot]) {
        if let ownedWindow {
            self.ownedWindow = current.first(where: { $0.identity == ownedWindow.identity })
            if self.ownedWindow == nil {
                claimWasResolved = true
            }
            return
        }
        guard !claimWasResolved else { return }

        let candidates = current.filter {
            !baseline.contains($0.identity) && $0.frame.width > 320 && $0.frame.height > 240
        }
        guard candidates.count <= 1 else {
            claimWasResolved = true
            return
        }
        guard let candidate = candidates.first else { return }
        ownedWindow = candidate
        claimWasResolved = true
    }
}

@MainActor
final class SystemSettingsAccessibilityController: AccessibilitySettingsSession {
    private static let bundleIdentifier = "com.apple.systempreferences"
    private static let accessibilityURL = URL(
        string: "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility"
    )

    private var ownership: SystemSettingsWindowOwnership?

    func openAccessibility() {
        ownership = SystemSettingsWindowOwnership(
            baseline: Set(Self.windows().map(\.identity))
        )
        guard let url = Self.accessibilityURL else { return }
        NSWorkspace.shared.open(url)
    }

    func refreshOwnership() {
        ownership?.refresh(current: Self.windows())
    }

    func closeOwnedWindow() {
        refreshOwnership()
        guard let ownedWindow = ownership?.ownedWindow else { return }
        let application = AXUIElementCreateApplication(ownedWindow.identity.processID)
        guard let window = Self.accessibilityWindow(in: application, matching: ownedWindow.frame),
              let closeButton = Self.elementAttribute(kAXCloseButtonAttribute, of: window) else {
            return
        }
        guard AXUIElementPerformAction(closeButton, kAXPressAction as CFString) == .success else { return }
        ownership = nil
    }

    func frontmostWindowFrame() -> CGRect? {
        guard NSWorkspace.shared.frontmostApplication?.bundleIdentifier == Self.bundleIdentifier else {
            return nil
        }
        guard let largest = Self.windows().max(by: {
            $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height
        }) else {
            return nil
        }
        return Self.appKitFrame(from: largest.frame)
    }

    private static func windows() -> [SystemSettingsWindowSnapshot] {
        let processIDs = Set(NSRunningApplication.runningApplications(
            withBundleIdentifier: bundleIdentifier
        ).map(\.processIdentifier))
        guard !processIDs.isEmpty,
              let windowInfo = CGWindowListCopyWindowInfo(
                [.optionAll, .excludeDesktopElements],
                .zero
              ) as? [[String: Any]] else {
            return []
        }

        return windowInfo.compactMap { info in
            guard let owner = info[kCGWindowOwnerPID as String] as? NSNumber,
                  let number = info[kCGWindowNumber as String] as? NSNumber,
                  let layer = info[kCGWindowLayer as String] as? NSNumber,
                  layer.intValue == 0,
                  processIDs.contains(owner.int32Value),
                  let bounds = info[kCGWindowBounds as String] as? NSDictionary,
                  let frame = CGRect(dictionaryRepresentation: bounds) else {
                return nil
            }
            guard frame.origin.x.isFinite,
                  frame.origin.y.isFinite,
                  frame.width.isFinite,
                  frame.height.isFinite,
                  frame.width > 0,
                  frame.height > 0 else {
                return nil
            }
            return SystemSettingsWindowSnapshot(
                identity: SystemSettingsWindowIdentity(
                    processID: owner.int32Value,
                    windowID: number.uint32Value
                ),
                frame: frame
            )
        }
    }

    private static func accessibilityWindow(
        in application: AXUIElement,
        matching expectedFrame: CGRect
    ) -> AXUIElement? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            application,
            kAXWindowsAttribute as CFString,
            &value
        ) == .success,
        let windows = value as? [AXUIElement] else {
            return nil
        }
        let matches = windows.filter { window in
            guard let frame = accessibilityFrame(of: window) else { return false }
            return approximatelyEqual(frame, expectedFrame)
        }
        guard matches.count == 1 else { return nil }
        return matches[0]
    }

    private static func accessibilityFrame(of window: AXUIElement) -> CGRect? {
        var positionValue: CFTypeRef?
        var sizeValue: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            window,
            kAXPositionAttribute as CFString,
            &positionValue
        ) == .success,
        AXUIElementCopyAttributeValue(
            window,
            kAXSizeAttribute as CFString,
            &sizeValue
        ) == .success,
        let position = axValue(positionValue),
        let size = axValue(sizeValue),
        AXValueGetType(position) == .cgPoint,
        AXValueGetType(size) == .cgSize else {
            return nil
        }
        var origin = CGPoint.zero
        var dimensions = CGSize.zero
        guard AXValueGetValue(position, .cgPoint, &origin),
              AXValueGetValue(size, .cgSize, &dimensions) else {
            return nil
        }
        return CGRect(origin: origin, size: dimensions)
    }

    private static func elementAttribute(_ attribute: String, of element: AXUIElement) -> AXUIElement? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success,
              let value,
              CFGetTypeID(value) == AXUIElementGetTypeID() else {
            return nil
        }
        return unsafeDowncast(value, to: AXUIElement.self)
    }

    private static func axValue(_ value: CFTypeRef?) -> AXValue? {
        guard let value, CFGetTypeID(value) == AXValueGetTypeID() else { return nil }
        return unsafeDowncast(value, to: AXValue.self)
    }

    private static func approximatelyEqual(_ lhs: CGRect, _ rhs: CGRect) -> Bool {
        let tolerance: CGFloat = 2
        return abs(lhs.minX - rhs.minX) <= tolerance
            && abs(lhs.minY - rhs.minY) <= tolerance
            && abs(lhs.width - rhs.width) <= tolerance
            && abs(lhs.height - rhs.height) <= tolerance
    }

    private static func appKitFrame(from cgFrame: CGRect) -> CGRect {
        let screens = NSScreen.screens.compactMap { screen -> (frame: CGRect, displayBounds: CGRect)? in
            guard let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else {
                return nil
            }
            return (screen.frame, CGDisplayBounds(CGDirectDisplayID(number.uint32Value)))
        }
        guard let screen = screens
            .filter({ $0.displayBounds.intersects(cgFrame) })
            .max(by: {
                $0.displayBounds.intersection(cgFrame).width * $0.displayBounds.intersection(cgFrame).height
                    < $1.displayBounds.intersection(cgFrame).width * $1.displayBounds.intersection(cgFrame).height
            }) else {
            return cgFrame
        }
        let localX = cgFrame.minX - screen.displayBounds.minX
        let localY = cgFrame.minY - screen.displayBounds.minY
        return CGRect(
            x: screen.frame.minX + localX,
            y: screen.frame.maxY - localY - cgFrame.height,
            width: cgFrame.width,
            height: cgFrame.height
        )
    }
}
