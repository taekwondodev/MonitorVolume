import ProArtVolumeCore

struct MeasuredMonitorController: MonitorControlling {
    private let base: any MonitorControlling
    private let recorder: LatencyRecorder

    init(base: any MonitorControlling, recorder: LatencyRecorder) {
        self.base = base
        self.recorder = recorder
    }

    @concurrent
    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        guard let context = ControlMeasurementTaskContext.current else {
            return try await base.readState()
        }
        recorder.record(stage: .ddcReadStarted, context: context)
        do {
            let state = try await base.readState()
            recorder.record(stage: .ddcReadCompleted, context: context, outcome: .success)
            return state
        } catch {
            recorder.record(stage: .ddcReadCompleted, context: context, outcome: .failure)
            throw error
        }
    }

    @concurrent
    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        guard let context = ControlMeasurementTaskContext.current else {
            return try await base.writeVolume(volume)
        }
        recorder.record(stage: .ddcWriteReadBackStarted, context: context)
        do {
            let confirmed = try await base.writeVolume(volume)
            recorder.record(stage: .ddcWriteReadBackCompleted, context: context, outcome: .success)
            return confirmed
        } catch {
            recorder.record(stage: .ddcWriteReadBackCompleted, context: context, outcome: .failure)
            throw error
        }
    }

    @concurrent
    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        guard let context = ControlMeasurementTaskContext.current else {
            return try await base.writeMute(mute)
        }
        recorder.record(stage: .ddcWriteReadBackStarted, context: context)
        do {
            let confirmed = try await base.writeMute(mute)
            recorder.record(stage: .ddcWriteReadBackCompleted, context: context, outcome: .success)
            return confirmed
        } catch {
            recorder.record(stage: .ddcWriteReadBackCompleted, context: context, outcome: .failure)
            throw error
        }
    }
}

struct MeasuredActiveAudioOutputReader: ActiveAudioOutputReading {
    private let base: any ActiveAudioOutputReading
    private let recorder: LatencyRecorder

    init(base: any ActiveAudioOutputReading, recorder: LatencyRecorder) {
        self.base = base
        self.recorder = recorder
    }

    func isTargetActive() async throws(MonitorRepositoryError) -> Bool {
        guard let context = ControlMeasurementTaskContext.current else {
            return try await base.isTargetActive()
        }
        recorder.record(stage: .activeOutputStarted, context: context)
        do {
            let isActive = try await base.isTargetActive()
            recorder.record(stage: .activeOutputCompleted, context: context, outcome: .success)
            return isActive
        } catch {
            recorder.record(stage: .activeOutputCompleted, context: context, outcome: .failure)
            throw error
        }
    }
}
