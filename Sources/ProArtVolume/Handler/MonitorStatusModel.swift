import Observation
import ProArtVolumeCore

@MainActor
@Observable
final class MonitorStatusModel {
    private let service: VolumeControlService
    private let activeOutput: CoreAudioOutputRepository
    private let routingSnapshot: MediaKeyRoutingSnapshot
    private let mediaKeyInterceptor: MediaKeyInterceptor
    private let osd: VolumeOSDPresenter
    private let latencyRecorder: LatencyRecorder?

    private var latestRevision: UInt64?
    private var commandTask: Task<Void, Never>?
    private var commandGeneration: UInt64 = 0
    private var mediaCommandTasks: [UInt64: Task<Void, Never>] = [:]
    private var mediaCommandGeneration: UInt64 = 0
    private var lastOSDRevision: UInt64?
    private var activeOutputObservation: ActiveAudioOutputObservation?
    private var outputRefreshTask: Task<Void, Never>?
    private var mediaKeyPermissionRefreshTask: Task<Void, Never>?

    private(set) var status: MonitorStatus?
    private(set) var draftVolume: VolumeLevel?
    private(set) var mediaKeyPermissionState: MediaKeyPermissionState

    init(
        service: VolumeControlService,
        activeOutput: CoreAudioOutputRepository,
        latencyRecorder: LatencyRecorder? = nil
    ) {
        self.service = service
        self.activeOutput = activeOutput
        self.latencyRecorder = latencyRecorder
        osd = VolumeOSDPresenter(latencyRecorder: latencyRecorder)
        let routingSnapshot = MediaKeyRoutingSnapshot()
        self.routingSnapshot = routingSnapshot
        mediaKeyInterceptor = MediaKeyInterceptor(routingSnapshot: routingSnapshot)
        mediaKeyPermissionState = mediaKeyInterceptor.permissionState
        mediaKeyInterceptor.delegate = self
    }

    isolated deinit {
        commandTask?.cancel()
        outputRefreshTask?.cancel()
        mediaKeyPermissionRefreshTask?.cancel()
        for task in mediaCommandTasks.values {
            task.cancel()
        }
        mediaKeyInterceptor.stop()
    }

    func activateMediaKeyControl() {
        refreshMediaKeyPermissions()
        if activeOutputObservation == nil {
            let routingSnapshot = routingSnapshot
            activeOutputObservation = try? activeOutput.observeDefaultOutputChanges { [weak self, routingSnapshot] in
                routingSnapshot.update(false)
                Task { @MainActor [weak self] in
                    self?.scheduleOutputRefresh()
                }
            }
        }
        scheduleOutputRefresh()
    }

    func refreshMediaKeyPermissions() {
        mediaKeyInterceptor.refreshPermissions()
        mediaKeyPermissionState = mediaKeyInterceptor.permissionState
    }

    func requestMediaKeyPermissions() {
        mediaKeyInterceptor.requestPermissions()
        mediaKeyPermissionState = mediaKeyInterceptor.permissionState
        beginMediaKeyPermissionRefresh()
    }

    func refresh() async {
        apply(await service.refresh())
    }

    func updateDraftVolume(_ rawValue: Double) {
        guard let volume = VolumeLevel(rawValue) else {
            return
        }
        draftVolume = volume
    }

    func commitDraftVolume() {
        guard let volume = draftVolume else {
            return
        }
        runCommand {
            await self.service.enqueueVolume(volume)
        }
    }

    func setMuted(_ muted: Bool) {
        let mute: MuteState = muted ? .muted : .unmuted
        runCommand {
            await self.service.enqueueMute(mute)
        }
    }

    private func runCommand(_ enqueue: @escaping @MainActor () async -> Void) {
        let precedingTask = commandTask
        commandGeneration += 1
        let generation = commandGeneration
        commandTask = Task {
            defer {
                if commandGeneration == generation {
                    commandTask = nil
                }
            }
            await precedingTask?.value
            await enqueue()
            let snapshot = await service.waitForPendingCommands()
            apply(snapshot)
        }
    }

    private func apply(_ snapshot: MonitorSnapshot) {
        if let latestRevision, snapshot.revision < latestRevision {
            return
        }
        latestRevision = snapshot.revision
        status = snapshot.status
        switch snapshot.status {
        case let .confirmed(output, state), let .commandFailure(output, state, _):
            routingSnapshot.update(output == .active)
            draftVolume = state.volume
        case .unavailable, .failure:
            routingSnapshot.update(false)
            draftVolume = nil
        }
    }

    private func scheduleOutputRefresh() {
        outputRefreshTask?.cancel()
        outputRefreshTask = Task { [weak self] in
            guard let self, !Task.isCancelled else {
                return
            }
            await refresh()
        }
    }

    private func beginMediaKeyPermissionRefresh() {
        mediaKeyPermissionRefreshTask?.cancel()
        mediaKeyPermissionRefreshTask = Task { [weak self] in
            for _ in 0..<120 {
                do {
                    try await Task.sleep(for: .seconds(1))
                } catch {
                    return
                }

                guard let self else {
                    return
                }

                refreshMediaKeyPermissions()
                if mediaKeyPermissionState == .granted {
                    return
                }
            }
        }
    }

    private func runMediaCommand(
        _ command: MediaKeyCommand,
        measurementID: ControlMeasurementID?
    ) {
        mediaCommandGeneration += 1
        let generation = mediaCommandGeneration
        let task = Task { [weak self] in
            guard let self else {
                return
            }
            switch command {
            case let .step(step):
                await service.enqueueVolumeStep(step, measurementID: measurementID)
            case .toggleMute:
                await service.enqueueMuteToggle(measurementID: measurementID)
            }
            let snapshot = await service.waitForPendingCommands()
            guard !Task.isCancelled else {
                mediaCommandTasks[generation] = nil
                return
            }
            apply(snapshot)
            presentOSD(for: snapshot)
            mediaCommandTasks[generation] = nil
        }
        mediaCommandTasks[generation] = task
    }

    private func presentOSD(for snapshot: MonitorSnapshot) {
        let interactionIDs = latencyRecorder?.takePendingPresentationIDs() ?? []
        guard snapshot.revision != lastOSDRevision else {
            return
        }
        lastOSDRevision = snapshot.revision
        guard case let .confirmed(.active, state) = snapshot.status else {
            return
        }
        osd.show(
            state,
            interactionIDs: interactionIDs
        )
    }

    private var confirmedMuteState: Bool? {
        switch status {
        case let .confirmed(_, state), let .commandFailure(_, state, _):
            state.mute == .muted
        case .unavailable, .failure, nil:
            nil
        }
    }
}

extension MonitorStatusModel: MediaKeyInterceptorDelegate {
    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, received command: MediaKeyCommand) {
        let measurementID = latencyRecorder?.beginInteraction(
            command: command,
            startingMuted: confirmedMuteState
        )
        if let measurementID {
            latencyRecorder?.record(
                stage: .commandEnqueueRequested,
                interactionIDs: [measurementID]
            )
        }
        runMediaCommand(command, measurementID: measurementID)
    }
}
