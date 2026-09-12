import MonitorTransport

package struct DDCMonitorRepository: MonitorControlling {
    package init() {}

    @concurrent
    package func readState(for target: MonitorIdentity) async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        let result = PAVDDCReadTargetState(
            target.manufacturer,
            target.productID,
            target.serial
        )
        switch result.status {
        case PAVDDCStatusTargetUnavailable:
            return nil
        case PAVDDCStatusReadFailure:
            throw .readFailure
        case PAVDDCStatusMalformedResponse:
            throw .malformedResponse
        case PAVDDCStatusSuccess:
            guard result.volumeMaximum == 100,
                  let volume = VolumeLevel(Int(result.volumeCurrent)) else {
                throw .malformedResponse
            }
            let mute: MonitorMuteState
            switch result.muteStatus {
            case PAVDDCStatusSuccess:
                guard result.muteMaximum == 2 else { throw .malformedResponse }
                mute = .supported(try MuteState(hardwareValue: result.muteCurrent))
            case PAVDDCStatusUnsupported:
                mute = .unsupported
            case PAVDDCStatusReadFailure:
                throw .readFailure
            default:
                throw .malformedResponse
            }
            return ConfirmedMonitorState(volume: volume, mute: mute)
        default:
            throw .malformedResponse
        }
    }

    @concurrent
    package func writeVolume(
        _ volume: VolumeLevel,
        for target: MonitorIdentity
    ) async throws(MonitorRepositoryError) -> VolumeLevel {
        let result = PAVDDCWriteTargetVolume(
            target.manufacturer,
            target.productID,
            target.serial,
            UInt16(volume.rawValue)
        )
        try validateWriteStatus(result.status)
        guard result.maximum == 100,
              let confirmed = VolumeLevel(Int(result.current)) else {
            throw .malformedResponse
        }
        guard confirmed == volume else {
            throw .readBackMismatch
        }
        return confirmed
    }

    @concurrent
    package func writeMute(
        _ mute: MuteState,
        for target: MonitorIdentity
    ) async throws(MonitorRepositoryError) -> MuteState {
        let result = PAVDDCWriteTargetMute(
            target.manufacturer,
            target.productID,
            target.serial,
            mute.hardwareValue
        )
        try validateWriteStatus(result.status)
        guard result.maximum == 2 else {
            throw .malformedResponse
        }
        let confirmed = try MuteState(hardwareValue: result.current)
        guard confirmed == mute else {
            throw .readBackMismatch
        }
        return confirmed
    }

    private func validateWriteStatus(_ status: PAVDDCStatus) throws(MonitorRepositoryError) {
        switch status {
        case PAVDDCStatusSuccess:
            return
        case PAVDDCStatusTargetUnavailable, PAVDDCStatusWriteFailure, PAVDDCStatusUnsupported:
            throw .writeFailure
        case PAVDDCStatusReadFailure:
            throw .readFailure
        case PAVDDCStatusMalformedResponse:
            throw .malformedResponse
        default:
            throw .malformedResponse
        }
    }
}
