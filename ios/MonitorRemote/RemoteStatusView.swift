import SwiftUI
import UIKit

struct RemoteStatusView: View {
    let status: RemoteStatus

    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(spacing: 8) {
            Label {
                Text(status.label)
            } icon: {
                Image(systemName: status.systemImage)
            }
            .font(.headline)
            .foregroundStyle(status == .connected ? .primary : .secondary)
            .contentTransition(.symbolEffect(.replace))
            .animation(.default, value: status)

            if status == .localNetworkDenied, let settings = URL(string: UIApplication.openSettingsURLString) {
                Button("Open Settings") {
                    openURL(settings)
                }
                .buttonStyle(.glass)
            }
        }
        .accessibilityElement(children: .contain)
    }
}
