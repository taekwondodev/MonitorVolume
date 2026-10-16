import AppKit
import MonitorVolumeCore

enum MediaKeyCode {
    static let volumeUp = 0
    static let volumeDown = 1
    static let mute = 7

    static func value(for key: MediaKey) -> Int {
        switch key {
        case .volumeUp:
            volumeUp
        case .volumeDown:
            volumeDown
        case .mute:
            mute
        }
    }
}

enum MediaKeyState {
    static let down = 0xA
    static let up = 0xB

    static func value(for phase: MediaKeyPhase) -> Int {
        switch phase {
        case .down:
            down
        case .up:
            up
        }
    }
}

enum MediaKeyEventParser {
    static let mediaKeySubtype = 8

    static func parse(_ event: CGEvent) -> MediaKeyEvent? {
        guard let event = NSEvent(cgEvent: event),
              event.type == .systemDefined,
              event.subtype.rawValue == mediaKeySubtype else {
            return nil
        }
        return parse(systemDefinedSubtype: Int(event.subtype.rawValue), data1: event.data1)
    }

    static func parse(systemDefinedSubtype: Int, data1: Int) -> MediaKeyEvent? {
        guard systemDefinedSubtype == mediaKeySubtype else {
            return nil
        }
        let keyCode = (data1 & 0xFFFF0000) >> 16
        let keyState = (data1 & 0x0000FF00) >> 8
        guard let key = key(for: keyCode), let phase = phase(for: keyState) else {
            return nil
        }
        return MediaKeyEvent(key: key, phase: phase)
    }

    private static func key(for rawValue: Int) -> MediaKey? {
        switch rawValue {
        case MediaKeyCode.volumeUp:
            .volumeUp
        case MediaKeyCode.volumeDown:
            .volumeDown
        case MediaKeyCode.mute:
            .mute
        default:
            nil
        }
    }

    private static func phase(for rawValue: Int) -> MediaKeyPhase? {
        switch rawValue {
        case MediaKeyState.down:
            .down
        case MediaKeyState.up:
            .up
        default:
            nil
        }
    }
}
