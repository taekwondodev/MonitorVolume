import ProArtVolumeCore
import SwiftUI

struct VolumeOSDView: View {
    let state: VolumeIntent
    var entered = true
    var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var valueText: String {
        state.mute == .muted ? "Muted" : "\(state.volume.rawValue)%"
    }

    private var completedSteps: Int {
        state.mute == .muted ? 0 : state.volume.rawValue / 5
    }

    private var speakerSymbol: String {
        if state.mute == .muted {
            return "speaker.slash.fill"
        }
        switch state.volume.rawValue {
        case 0:
            return "speaker.fill"
        case 1..<34:
            return "speaker.wave.1.fill"
        case 34..<67:
            return "speaker.wave.2.fill"
        default:
            return "speaker.wave.3.fill"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("ASUS PA279CV")
                    .font(.headline)
                Spacer()
                Text(valueText)
                    .monospacedDigit()
                    .bold()
            }
            HStack(spacing: 10) {
                Image(systemName: speakerSymbol)
                    .frame(width: 20)
                VStack(spacing: 5) {
                    VolumeLevelBar(state: state)
                        .padding(.vertical, 4)
                    VolumeStepIndicators(completedSteps: completedSteps)
                }
                Image(systemName: "speaker.wave.3.fill")
                    .frame(width: 20)
            }
        }
        .padding(18)
        .opacity(pulse ? 0.65 : 1)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 24))
        .overlay {
            RoundedRectangle(cornerRadius: 24)
                .stroke(.primary.tertiary, lineWidth: 1)
        }
        .padding(4)
        .scaleEffect(reduceMotion || entered ? 1 : 0.985)
        .animation(.easeOut(duration: 0.12), value: entered)
        .animation(.easeOut(duration: 0.10), value: pulse)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("ASUS PA279CV volume")
        .accessibilityValue(valueText)
    }
}