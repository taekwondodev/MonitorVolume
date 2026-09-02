package actor VolumeControlService {
    private let monitor: any MonitorStateReading
    private let activeOutput: any ActiveAudioOutputReading

    package init(monitor: any MonitorStateReading, activeOutput: any ActiveAudioOutputReading) {
        self.monitor = monitor
        self.activeOutput = activeOutput
    }

    package func refresh() async -> MonitorStatus {
        do {
            guard let state = try await monitor.readState() else {
                return .unavailable
            }
            let output: AudioOutputState = try await activeOutput.isTargetActive() ? .active : .inactive
            return .confirmed(output: output, state: state)
        } catch let error {
            return .failure(error)
        }
    }
}
