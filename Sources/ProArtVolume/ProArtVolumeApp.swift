import ProArtVolumeCore
import AppKit

@main
enum ProArtVolumeApp {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
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
        let eligibility = ControlEligibility()
        let service = IntentControlService(
            monitor: monitor,
            activeOutput: serviceActiveOutput,
            eligibility: eligibility,
            observer: latencyRecorder?.makeServiceObserver()
        )
        let coordinator = ApplicationCoordinator(
            service: service,
            output: activeOutput,
            eligibility: eligibility,
            recorder: latencyRecorder,
            diagnostics: InputLifecycleDiagnostics.configured()
        )
        app.delegate = coordinator
        withExtendedLifetime(coordinator) {
            app.run()
        }
    }
}
