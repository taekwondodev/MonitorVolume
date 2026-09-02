import ProArtVolumeCore
import SwiftUI

@main
struct ProArtVolumeApp: App {
    @State private var model: MonitorStatusModel

    init() {
        let identity = MonitorIdentity.target
        let service = VolumeControlService(
            monitor: DDCMonitorRepository(identity: identity),
            activeOutput: CoreAudioOutputRepository(identity: identity)
        )
        model = MonitorStatusModel(service: service)
    }

    var body: some Scene {
        MenuBarExtra {
            MonitorStatusView(model: model)
        } label: {
            Label(AppIdentity.name, systemImage: "speaker.wave.2")
        }
        .menuBarExtraStyle(.window)
    }
}
