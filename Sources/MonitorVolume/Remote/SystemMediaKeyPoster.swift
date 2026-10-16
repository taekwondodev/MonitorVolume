import AppKit
import MonitorVolumeCore

@MainActor
final class SystemMediaKeyPoster {
    func post(_ event: MediaKeyEvent) {
        let data = Self.eventData(for: event)
        NSEvent.otherEvent(
            with: .systemDefined,
            location: .zero,
            modifierFlags: NSEvent.ModifierFlags(rawValue: UInt(data.modifierFlags)),
            timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: 0,
            context: nil,
            subtype: Int16(data.subtype),
            data1: data.data1,
            data2: -1
        )?.cgEvent?.post(tap: .cghidEventTap)
    }

    nonisolated static func eventData(for event: MediaKeyEvent) -> SystemDefinedMediaKeyData {
        let state = MediaKeyState.value(for: event.phase)
        return SystemDefinedMediaKeyData(
            subtype: MediaKeyEventParser.mediaKeySubtype,
            data1: (MediaKeyCode.value(for: event.key) << 16) | (state << 8),
            modifierFlags: state << 8
        )
    }
}

struct SystemDefinedMediaKeyData: Equatable {
    let subtype: Int
    let data1: Int
    let modifierFlags: Int
}
