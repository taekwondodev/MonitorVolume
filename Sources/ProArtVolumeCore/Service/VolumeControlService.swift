package actor VolumeControlService {
    private enum PendingCommand: Sendable {
        case refresh
        case volume(VolumeLevel)
        case mute(MuteState)
        case mediaVolumeAdjustment(Int, [ControlMeasurementID])
        case mediaMuteToggle([ControlMeasurementID])

        var isVolume: Bool {
            if case .volume = self {
                return true
            }
            return false
        }

        var isMute: Bool {
            if case .mute = self {
                return true
            }
            return false
        }

        var measurementContext: ControlMeasurementContext? {
            let interactionIDs: [ControlMeasurementID] = switch self {
            case let .mediaVolumeAdjustment(_, interactionIDs), let .mediaMuteToggle(interactionIDs):
                interactionIDs
            case .refresh, .volume, .mute:
                []
            }
            return interactionIDs.isEmpty ? nil : ControlMeasurementContext(interactionIDs: interactionIDs)
        }

    }

    private let monitor: any MonitorControlling
    private let activeOutput: any ActiveAudioOutputReading
    private let measurementObserver: ControlMeasurementObserver?

    private var revision: UInt64 = 0
    private var status: MonitorStatus = .unavailable
    private var pendingCommands: [PendingCommand] = []
    private var commandTask: Task<Void, Never>?

    package init(
        monitor: any MonitorControlling,
        activeOutput: any ActiveAudioOutputReading,
        measurementObserver: ControlMeasurementObserver? = nil
    ) {
        self.monitor = monitor
        self.activeOutput = activeOutput
        self.measurementObserver = measurementObserver
    }

    package func refresh() async -> MonitorSnapshot {
        pendingCommands.append(.refresh)
        startCommandTaskIfNeeded()
        return await waitForPendingCommands()
    }

    package func enqueueVolume(_ volume: VolumeLevel) {
        pendingCommands.removeAll { $0.isVolume }
        pendingCommands.append(.volume(volume))
        startCommandTaskIfNeeded()
    }

    package func enqueueMute(_ mute: MuteState) {
        pendingCommands.removeAll { $0.isMute }
        pendingCommands.append(.mute(mute))
        startCommandTaskIfNeeded()
    }

    package func enqueueVolumeStep(
        _ step: VolumeStep,
        measurementID: ControlMeasurementID? = nil
    ) {
        guard !Task.isCancelled else {
            return
        }
        var adjustment = step.points
        let enqueuedInteractionIDs = measurementID.map { [$0] } ?? []
        var interactionIDs = enqueuedInteractionIDs
        if case let .mediaVolumeAdjustment(points, pendingInteractionIDs) = pendingCommands.last {
            adjustment += points
            interactionIDs = pendingInteractionIDs + interactionIDs
            pendingCommands.removeLast()
        }
        pendingCommands.append(.mediaVolumeAdjustment(adjustment, interactionIDs))
        recordEnqueued(interactionIDs: enqueuedInteractionIDs)
        startCommandTaskIfNeeded()
    }

    package func enqueueMuteToggle(measurementID: ControlMeasurementID? = nil) {
        guard !Task.isCancelled else {
            return
        }
        let interactionIDs = measurementID.map { [$0] } ?? []
        pendingCommands.append(.mediaMuteToggle(interactionIDs))
        recordEnqueued(interactionIDs: interactionIDs)
        startCommandTaskIfNeeded()
    }

    package func waitForPendingCommands() async -> MonitorSnapshot {
        while let task = commandTask {
            await task.value
        }
        return snapshot
    }

    private var snapshot: MonitorSnapshot {
        MonitorSnapshot(revision: revision, status: status)
    }

    private var confirmedContext: (output: AudioOutputState, state: ConfirmedMonitorState)? {
        switch status {
        case let .confirmed(output, state), let .commandFailure(output, state, _):
            return (output, state)
        case .unavailable, .failure:
            return nil
        }
    }

    private func startCommandTaskIfNeeded() {
        guard commandTask == nil else {
            return
        }
        commandTask = Task {
            await self.drainCommands()
        }
    }

    private func recordEnqueued(interactionIDs: [ControlMeasurementID]) {
        guard !interactionIDs.isEmpty else {
            return
        }
        measurementObserver?.record(
            .commandEnqueued,
            context: ControlMeasurementContext(interactionIDs: interactionIDs)
        )
    }

    private func drainCommands() async {
        while let command = pendingCommands.first {
            pendingCommands.removeFirst()
            if let context = command.measurementContext {
                measurementObserver?.record(.commandStarted, context: context)
                await ControlMeasurementTaskContext.$current.withValue(context) {
                    await perform(command)
                }
                measurementObserver?.record(.commandCompleted, context: context)
            } else {
                await perform(command)
            }
        }
        commandTask = nil
    }

    private func perform(_ command: PendingCommand) async {
        switch command {
        case .refresh:
            await performRefresh()
        case let .volume(volume):
            await performVolume(volume)
        case let .mute(mute):
            await performMute(mute)
        case let .mediaVolumeAdjustment(points, _):
            await performMediaVolumeAdjustment(points)
        case .mediaMuteToggle:
            await performMediaMuteToggle()
        }
    }

    private func performRefresh() async {
        do {
            guard let state = try await monitor.readState() else {
                publish(.unavailable)
                return
            }
            let output: AudioOutputState = try await activeOutput.isTargetActive() ? .active : .inactive
            publish(.confirmed(output: output, state: state))
        } catch let error {
            publish(.failure(error))
        }
    }

    private func performVolume(_ requested: VolumeLevel) async {
        guard let context = await confirmedContextForCommand() else {
            return
        }
        do {
            let confirmed = try await monitor.writeVolume(requested)
            publish(
                .confirmed(
                    output: context.output,
                    state: ConfirmedMonitorState(volume: confirmed, mute: context.state.mute)
                )
            )
        } catch let error {
            publish(.commandFailure(output: context.output, state: context.state, error: error))
        }
    }

    private func performMute(_ requested: MuteState) async {
        guard let context = await confirmedContextForCommand() else {
            return
        }
        do {
            let confirmed = try await monitor.writeMute(requested)
            publish(
                .confirmed(
                    output: context.output,
                    state: ConfirmedMonitorState(volume: context.state.volume, mute: confirmed)
                )
            )
        } catch let error {
            publish(.commandFailure(output: context.output, state: context.state, error: error))
        }
    }

    private func performMediaVolumeAdjustment(_ points: Int) async {
        do {
            guard try await activeOutput.isTargetActive() else {
                publishInactiveContext()
                return
            }
            guard let current = try await monitor.readState() else {
                publish(.unavailable)
                return
            }
            let requested = current.volume.adjusting(by: points)
            do {
                let confirmed = if requested == current.volume {
                    current.volume
                } else {
                    try await monitor.writeVolume(requested)
                }
                let confirmedMute = if current.mute == .muted {
                    try await monitor.writeMute(.unmuted)
                } else {
                    current.mute
                }
                publish(
                    .confirmed(
                        output: .active,
                        state: ConfirmedMonitorState(volume: confirmed, mute: confirmedMute)
                    )
                )
            } catch let error {
                publish(.commandFailure(output: .active, state: current, error: error))
            }
        } catch let error {
            publishMediaCommandFailure(error)
        }
    }

    private func performMediaMuteToggle() async {
        do {
            guard try await activeOutput.isTargetActive() else {
                publishInactiveContext()
                return
            }
            guard let current = try await monitor.readState() else {
                publish(.unavailable)
                return
            }
            do {
                let confirmed = try await monitor.writeMute(current.mute.toggled)
                publish(
                    .confirmed(
                        output: .active,
                        state: ConfirmedMonitorState(volume: current.volume, mute: confirmed)
                    )
                )
            } catch let error {
                publish(.commandFailure(output: .active, state: current, error: error))
            }
        } catch let error {
            publishMediaCommandFailure(error)
        }
    }

    private func publishInactiveContext() {
        guard let context = confirmedContext else {
            return
        }
        publish(.confirmed(output: .inactive, state: context.state))
    }

    private func publishMediaCommandFailure(_ error: MonitorRepositoryError) {
        guard let context = confirmedContext else {
            publish(.failure(error))
            return
        }
        publish(.commandFailure(output: context.output, state: context.state, error: error))
    }

    private func confirmedContextForCommand() async -> (output: AudioOutputState, state: ConfirmedMonitorState)? {
        if let confirmedContext {
            return confirmedContext
        }
        await performRefresh()
        return confirmedContext
    }

    private func publish(_ newStatus: MonitorStatus) {
        revision += 1
        status = newStatus
    }
}
