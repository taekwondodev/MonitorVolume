import MonitorRemoteProtocol
import SwiftUI

/// A key that reports touch-down and lift-off, so holding it repeats like a held key.
struct RemoteKeyButton: View {
    let key: RemoteKey
    let controller: RemoteController

    @Environment(\.isEnabled) private var isEnabled
    @State private var isPressed = false

    var body: some View {
        Label(key.title, systemImage: key.systemImage)
            .labelStyle(.iconOnly)
            .font(.system(.largeTitle, weight: .semibold))
            .foregroundStyle(isEnabled ? .primary : .tertiary)
            .frame(maxWidth: .infinity, minHeight: 96)
            .contentShape(.rect)
            .scaleEffect(isPressed ? 0.9 : 1)
            .animation(.snappy(duration: 0.15), value: isPressed)
            .onLongPressGesture(minimumDuration: .infinity) {
            } onPressingChanged: { pressing in
                isPressed = pressing
                if pressing {
                    controller.press(key)
                } else {
                    controller.release(key)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(key.title)
            .accessibilityAddTraits(.isButton)
            .accessibilityAction {
                controller.tap(key)
            }
    }
}

extension RemoteKey {
    var title: LocalizedStringResource {
        switch self {
        case .volumeUp: "Volume Up"
        case .volumeDown: "Volume Down"
        case .mute: "Mute"
        }
    }

    var systemImage: String {
        switch self {
        case .volumeUp: "plus"
        case .volumeDown: "minus"
        case .mute: "speaker.slash.fill"
        }
    }
}
