import SwiftUI

struct VolumeStepIndicators: View {
    let completedSteps: Int

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                Capsule()
                    .fill(.quaternary)
                    .frame(width: proxy.size.width - VolumeLevelBar.height, height: 1)

                ForEach(1...20, id: \.self) { step in
                    Capsule()
                        .fill(style(for: step))
                        .frame(
                            width: step == completedSteps ? 2 : 1,
                            height: step == completedSteps ? 11 : 7
                        )
                        .position(
                            x: VolumeLevelBar.height / 2
                                + (proxy.size.width - VolumeLevelBar.height) * Double(step) / 20,
                            y: 5.5
                        )
                }
            }
        }
        .frame(height: 11)
    }

    private func style(for step: Int) -> HierarchicalShapeStyle {
        if completedSteps > 0, step == completedSteps {
            return .primary
        }
        if step < completedSteps {
            return .secondary
        }
        return .tertiary
    }
}