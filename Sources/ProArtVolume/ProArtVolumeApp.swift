import ProArtVolumeCore
import SwiftUI

@main
struct ProArtVolumeApp: App {
    @State private var model: MonitorStatusModel

    init() {
        let identity = MonitorIdentity.target
        let activeOutput = CoreAudioOutputRepository(identity: identity)
        let latencyRecorder: LatencyRecorder?
        do {
            latencyRecorder = try LatencyRecorder.configured()
        } catch {
            fatalError("Latency measurement setup failed: \(error.localizedDescription)")
        }
        let monitor: any MonitorControlling
        let serviceActiveOutput: any ActiveAudioOutputReading
        if let latencyRecorder {
            monitor = MeasuredMonitorController(
                base: DDCMonitorRepository(identity: identity),
                recorder: latencyRecorder
            )
            serviceActiveOutput = MeasuredActiveAudioOutputReader(
                base: activeOutput,
                recorder: latencyRecorder
            )
        } else {
            monitor = DDCMonitorRepository(identity: identity)
            serviceActiveOutput = activeOutput
        }
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: serviceActiveOutput,
            measurementObserver: latencyRecorder?.makeServiceObserver()
        )
        let model = MonitorStatusModel(
            service: service,
            activeOutput: activeOutput,
            latencyRecorder: latencyRecorder
        )
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
