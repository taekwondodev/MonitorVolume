import ProArtVolumeCore
import AppKit

@main
enum ProArtVolumeApp {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let identity = MonitorIdentity.target
        let activeOutput = CoreAudioOutputRepository(identity: identity)
        let eligibility = ControlEligibility()
        let service = IntentControlService(
            monitor: DDCMonitorRepository(identity: identity),
            activeOutput: activeOutput,
            eligibility: eligibility
        )
        let coordinator = ApplicationCoordinator(
            service: service,
            output: activeOutput,
            eligibility: eligibility,
            diagnostics: InputLifecycleDiagnostics.configured()
        )
        app.delegate = coordinator
        withExtendedLifetime(coordinator) {
            app.run()
        }
    }
}
