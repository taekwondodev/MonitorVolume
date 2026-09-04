import ProArtVolumeCore
import SwiftUI

struct VolumeLevelBar: View {
    static let height: CGFloat = 8

    let state: ConfirmedMonitorState

    private var progress: Double {
        state.mute == .muted ? 0 : Double(state.volume.rawValue) / 100
    }

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(.quaternary)
                if progress > 0 {
                    Capsule()
                        .fill(.primary)
                        .frame(
                            width: Self.height + (proxy.size.width - Self.height) * progress
                        )
                }
            }
        }
        .frame(height: Self.height)
    }
}