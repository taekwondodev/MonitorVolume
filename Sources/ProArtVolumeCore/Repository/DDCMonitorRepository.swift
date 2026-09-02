import MonitorTransport

package struct DDCMonitorRepository: MonitorControlling {
    private let identity: MonitorIdentity

    package init(identity: MonitorIdentity) {
        self.identity = identity
    }

    package func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        let result = PAVDDCReadTargetState(
            identity.manufacturer,
            identity.productID,
            identity.serial
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
                  result.muteMaximum == 2,
                  let volume = VolumeLevel(Int(result.volumeCurrent)) else {
                throw .malformedResponse
            }
            let mute = try MuteState(hardwareValue: result.muteCurrent)
            return ConfirmedMonitorState(volume: volume, mute: mute)
        default:
            throw .malformedResponse
        }
    }

    package func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        let result = PAVDDCWriteTargetVolume(
            identity.manufacturer,
            identity.productID,
            identity.serial,
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

    package func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        let result = PAVDDCWriteTargetMute(
            identity.manufacturer,
            identity.productID,
            identity.serial,
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
        case PAVDDCStatusTargetUnavailable, PAVDDCStatusWriteFailure:
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
