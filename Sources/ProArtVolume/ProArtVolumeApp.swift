import ProArtVolumeCore
import AppKit

@main
enum ProArtVolumeApp {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let activeOutput = CoreAudioOutputRepository()
        let eligibility = ControlEligibility()
        let service = IntentControlService(
            monitor: DDCMonitorRepository(),
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
