import SwiftUI

@main
struct ProArtVolumeApp: App {
    var body: some Scene {
        MenuBarExtra(AppIdentity.name, systemImage: "speaker.wave.2") {
            Text(AppIdentity.name)
                .padding()
        }
        .menuBarExtraStyle(.window)
    }
}
