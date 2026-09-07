import Darwin
import Foundation
import ProArtVolumeCore

@main
struct ProArtVolumeRuntimeProbe {
    static func main() async {
        let identity = MonitorIdentity.target
        let monitor = DDCMonitorRepository(identity: identity)
        let output = CoreAudioOutputRepository(identity: identity)
        if CommandLine.arguments.contains("--verify-controls") {
            let report = await HardwareProofService(monitor: monitor, output: output).run()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            do {
                FileHandle.standardOutput.write(try encoder.encode(report))
                exit(report.status == "passed" ? 0 : 5)
            } catch { exit(5) }
        }
        let status: MonitorStatus
        do {
            if let state = try await monitor.readState() {
                let active = try await output.isTargetActive()
                status = .confirmed(output: active ? .active : .inactive, state: state)
            } else {
                status = .unavailable
            }
        } catch { status = .failure(error) }
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
        case .failure(.writeFailure):
            payload = ["status": "write_failure"]
            exitCode = 5
        case .failure(.readBackMismatch):
            payload = ["status": "read_back_mismatch"]
            exitCode = 6
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
