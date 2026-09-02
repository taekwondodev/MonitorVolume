import Observation
import ProArtVolumeCore

@MainActor
@Observable
final class MonitorStatusModel {
    private let service: VolumeControlService

    private var latestRevision: UInt64?
    private var commandTask: Task<Void, Never>?
    private var commandGeneration: UInt64 = 0

    private(set) var status: MonitorStatus?
    private(set) var draftVolume: VolumeLevel?

    init(service: VolumeControlService) {
        self.service = service
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
        case let .confirmed(_, state), let .commandFailure(_, state, _):
            draftVolume = state.volume
        case .unavailable, .failure:
            draftVolume = nil
        }
    }
}
