import AppKit
import ProArtVolumeCore
import SwiftUI

struct MonitorStatusView: View {
    let model: MonitorStatusModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            statusContent
            Divider()
            Button("Quit ProArt Volume") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q")
        }
        .padding()
        .frame(width: 280)
        .task {
            await model.refresh()
        }
    }

    @ViewBuilder
    private var statusContent: some View {
        switch model.status {
        case nil:
            ProgressView("Reading ASUS PA279CV…")
        case let .confirmed(output, state):
            Label("ASUS PA279CV", systemImage: "display")
                .font(.headline)
            LabeledContent("Audio output", value: output == .active ? "Active" : "Inactive")
            LabeledContent("Volume", value: "\(state.volume.rawValue)%")
            LabeledContent("Mute", value: state.mute == .muted ? "Muted" : "Unmuted")
        case .unavailable:
            Label("ASUS PA279CV unavailable", systemImage: "display.trianglebadge.exclamationmark")
        case .failure(.malformedResponse):
            Label("Invalid monitor response", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        case .failure(.readFailure):
            Label("Unable to read monitor", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        }
    }
}
