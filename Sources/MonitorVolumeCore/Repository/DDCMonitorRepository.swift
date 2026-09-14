import MonitorTransport

package struct DDCMonitorRepository: MonitorControlling {
    package init() {}

    @concurrent
    package func readState(for target: MonitorIdentity) async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        let result = MVDDCReadTargetState(
            target.manufacturer,
            target.productID,
            target.serial
        )
        switch result.status {
        case MVDDCStatusTargetUnavailable:
            return nil
        case MVDDCStatusReadFailure:
            throw .readFailure
        case MVDDCStatusMalformedResponse:
            throw .malformedResponse
        case MVDDCStatusSuccess:
            guard result.volumeMaximum == 100,
                  let volume = VolumeLevel(Int(result.volumeCurrent)) else {
                throw .malformedResponse
            }
            let mute: MonitorMuteState
            switch result.muteStatus {
            case MVDDCStatusSuccess:
                guard result.muteMaximum == 2 else { throw .malformedResponse }
                mute = .supported(try MuteState(hardwareValue: result.muteCurrent))
            case MVDDCStatusUnsupported:
                mute = .unsupported
            case MVDDCStatusReadFailure:
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
        let result = MVDDCWriteTargetVolume(
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
        let result = MVDDCWriteTargetMute(
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

    private func validateWriteStatus(_ status: MVDDCStatus) throws(MonitorRepositoryError) {
        switch status {
        case MVDDCStatusSuccess:
            return
        case MVDDCStatusTargetUnavailable, MVDDCStatusWriteFailure, MVDDCStatusUnsupported:
            throw .writeFailure
        case MVDDCStatusReadFailure:
            throw .readFailure
        case MVDDCStatusMalformedResponse:
            throw .malformedResponse
        default:
            throw .malformedResponse
        }
    }
}
