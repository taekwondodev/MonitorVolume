import AppKit
import ProArtVolumeCore
import SwiftUI

struct MonitorStatusView: View {
    let model: MonitorStatusModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            statusContent
            permissionContent
            Divider()
            Button("Quit ProArt Volume") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q")
        }
        .padding()
        .frame(width: 280)
        .task {
            model.refreshMediaKeyPermissions()
            await model.refresh()
        }
    }

    @ViewBuilder
    private var permissionContent: some View {
        if let explanation = model.mediaKeyPermissionState.explanation {
            Label(explanation, systemImage: "keyboard.badge.ellipsis")
                .foregroundStyle(.secondary)
            Button("Enable Volume Keys") {
                model.requestMediaKeyPermissions()
            }
        }
    }

    @ViewBuilder
    private var statusContent: some View {
        switch model.status {
        case nil:
            ProgressView("Reading ASUS PA279CV…")
        case let .confirmed(output, state):
            confirmedContent(output: output, state: state)
        case let .commandFailure(output, state, error):
            confirmedContent(output: output, state: state)
            Label(commandErrorText(error), systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        case .unavailable:
            Label("ASUS PA279CV unavailable", systemImage: "display.trianglebadge.exclamationmark")
        case .failure(.malformedResponse):
            Label("Invalid monitor response", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        case .failure(.readFailure):
            Label("Unable to read monitor", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        case .failure(.writeFailure):
            Label("Unable to write monitor", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        case .failure(.readBackMismatch):
            Label("Monitor did not confirm the change", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        }
    }

    @ViewBuilder
    private func confirmedContent(output: AudioOutputState, state: ConfirmedMonitorState) -> some View {
        Label("ASUS PA279CV", systemImage: "display")
            .font(.headline)
        LabeledContent("Audio output", value: output == .active ? "Active" : "Inactive")
        HStack {
            Slider(
                value: Binding(
                    get: { Double(model.draftVolume?.rawValue ?? state.volume.rawValue) },
                    set: { rawValue in
                        model.updateDraftVolume(rawValue)
                    }
                ),
                in: 0...100,
                step: 1,
                onEditingChanged: { editing in
                    if !editing {
                        model.commitDraftVolume()
                    }
                }
            )
            .accessibilityLabel("Monitor volume")
            Text("\(model.draftVolume?.rawValue ?? state.volume.rawValue)%")
                .monospacedDigit()
                .frame(width: 36, alignment: .trailing)
        }
        Toggle(
            "Mute",
            isOn: Binding(
                get: { state.mute == .muted },
                set: { muted in
                    model.setMuted(muted)
                }
            )
        )
        .toggleStyle(.switch)
    }

    private func commandErrorText(_ error: MonitorRepositoryError) -> String {
        switch error {
        case .writeFailure:
            "Unable to write monitor"
        case .readBackMismatch:
            "Monitor did not confirm the change"
        case .malformedResponse:
            "Invalid monitor response"
        case .readFailure:
            "Unable to confirm monitor change"
        }
    }
}
