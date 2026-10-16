import SwiftUI

struct RemoteView: View {
    let controller: RemoteController

    var body: some View {
        VStack {
            RemoteStatusView(status: controller.status)
            Spacer()
            GlassEffectContainer {
                VStack(spacing: 32) {
                    VStack(spacing: 0) {
                        RemoteKeyButton(key: .volumeUp, controller: controller)
                        Divider()
                            .padding(.horizontal)
                        RemoteKeyButton(key: .volumeDown, controller: controller)
                    }
                    .frame(width: 120)
                    .glassEffect(.regular.interactive(), in: .capsule)

                    RemoteKeyButton(key: .mute, controller: controller)
                        .frame(width: 120)
                        .glassEffect(.regular.interactive(), in: .capsule)
                }
            }
            .disabled(controller.isEnabled == false)
            Spacer()
        }
        .padding()
        .sensoryFeedback(.impact(weight: .light), trigger: controller.sentPresses)
    }
}
