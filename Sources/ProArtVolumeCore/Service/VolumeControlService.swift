package actor VolumeControlService {
    private enum PendingCommand: Sendable {
        case refresh
        case volume(VolumeLevel)
        case mute(MuteState)

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
    }

    private let monitor: any MonitorControlling
    private let activeOutput: any ActiveAudioOutputReading

    private var revision: UInt64 = 0
    private var status: MonitorStatus = .unavailable
    private var pendingCommands: [PendingCommand] = []
    private var commandTask: Task<Void, Never>?

    package init(monitor: any MonitorControlling, activeOutput: any ActiveAudioOutputReading) {
        self.monitor = monitor
        self.activeOutput = activeOutput
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
            await drainCommands()
        }
    }

    private func drainCommands() async {
        while let command = pendingCommands.first {
            pendingCommands.removeFirst()
            switch command {
            case .refresh:
                await performRefresh()
            case let .volume(volume):
                await performVolume(volume)
            case let .mute(mute):
                await performMute(mute)
            }
        }
        commandTask = nil
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
