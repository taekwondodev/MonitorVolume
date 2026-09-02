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
        var status = await service.refresh().status
        var volumeWriteConfirmed = false
        var muteWriteConfirmed = false
        if CommandLine.arguments.contains("--verify-controls"),
           case let .confirmed(_, state) = status {
            await service.enqueueVolume(state.volume)
            status = await service.waitForPendingCommands().status
            if case let .confirmed(_, volumeState) = status,
               volumeState.volume == state.volume {
                volumeWriteConfirmed = true
                await service.enqueueMute(volumeState.mute)
                status = await service.waitForPendingCommands().status
                if case let .confirmed(_, muteState) = status,
                   muteState == volumeState {
                    muteWriteConfirmed = true
                }
            }
        }
        let payload: [String: Any]
        let exitCode: Int32
        switch status {
        case let .confirmed(output, state):
            payload = [
                "mute": state.mute == .muted ? "muted" : "unmuted",
                "output": output == .active ? "active" : "inactive",
                "status": "confirmed",
                "volume": state.volume.rawValue,
                "volume_write_confirmed": volumeWriteConfirmed,
                "mute_write_confirmed": muteWriteConfirmed,
            ]
            exitCode = 0
        case .unavailable:
            payload = ["status": "unavailable"]
            exitCode = 2
        case let .commandFailure(output, state, error):
            payload = [
                "error": commandErrorName(error),
                "mute": state.mute == .muted ? "muted" : "unmuted",
                "output": output == .active ? "active" : "inactive",
                "status": "command_failure",
                "volume": state.volume.rawValue,
            ]
            exitCode = 5
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

    private static func commandErrorName(_ error: MonitorRepositoryError) -> String {
        switch error {
        case .malformedResponse:
            "malformed_response"
        case .readFailure:
            "read_failure"
        case .writeFailure:
            "write_failure"
        case .readBackMismatch:
            "read_back_mismatch"
        }
    }
}
