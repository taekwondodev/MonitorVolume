import Darwin
import Foundation
import ProArtVolumeCore

@main
struct ProArtVolumeRuntimeProbe {
    static func main() async {
        let identity = MonitorIdentity.target
        let service = VolumeControlService(
            monitor: DDCMonitorRepository(identity: identity),
            activeOutput: CoreAudioOutputRepository(identity: identity)
        )
        let status = await service.refresh()
        let payload: [String: Any]
        let exitCode: Int32
        switch status {
        case let .confirmed(output, state):
            payload = [
                "mute": state.mute == .muted ? "muted" : "unmuted",
                "output": output == .active ? "active" : "inactive",
                "status": "confirmed",
                "volume": state.volume.rawValue,
            ]
            exitCode = 0
        case .unavailable:
            payload = ["status": "unavailable"]
            exitCode = 2
        case .failure(.malformedResponse):
            payload = ["status": "malformed_response"]
            exitCode = 3
        case .failure(.readFailure):
            payload = ["status": "read_failure"]
            exitCode = 4
        }
        guard let data = try? JSONSerialization.data(
            withJSONObject: payload,
            options: [.prettyPrinted, .sortedKeys]
        ) else {
            exit(5)
        }
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
        exit(exitCode)
    }
}
