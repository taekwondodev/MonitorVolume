import SwiftUI

@main
struct MonitorRemoteApp: App {
    @State private var controller = RemoteController(link: NetworkRemoteLink())
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RemoteView(controller: controller)
        }
        .onChange(of: scenePhase, initial: true) { _, phase in
            switch phase {
            case .active:
                controller.start()
            case .background:
                controller.enterBackground()
            case .inactive:
                break
            @unknown default:
                break
            }
        }
    }
}
