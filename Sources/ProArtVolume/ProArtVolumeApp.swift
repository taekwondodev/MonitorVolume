import ProArtVolumeCore
import SwiftUI

@main
struct ProArtVolumeApp: App {
    @State private var model: MonitorStatusModel

    init() {
        let identity = MonitorIdentity.target
        let activeOutput = CoreAudioOutputRepository(identity: identity)
        let service = VolumeControlService(
            monitor: DDCMonitorRepository(identity: identity),
            activeOutput: activeOutput
        )
        let model = MonitorStatusModel(service: service, activeOutput: activeOutput)
        model.activateMediaKeyControl()
        self.model = model
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
