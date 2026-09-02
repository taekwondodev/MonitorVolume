import MonitorTransport

package struct DDCMonitorRepository: MonitorStateReading {
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
                  let volume = VolumeLevel(Int(result.volumeCurrent)) else {
                throw .malformedResponse
            }
            let mute = try MuteState(hardwareValue: result.muteCurrent)
            return ConfirmedMonitorState(volume: volume, mute: mute)
        default:
            throw .malformedResponse
        }
    }
}
