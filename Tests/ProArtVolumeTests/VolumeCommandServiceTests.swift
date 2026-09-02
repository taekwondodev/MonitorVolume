import Testing
@testable import ProArtVolumeCore

struct VolumeCommandServiceTests {
    @Test
    func confirmsHardwareMuteWithoutChangingVolume() async throws {
        let volume = try #require(VolumeLevel(60))
        let initial = ConfirmedMonitorState(volume: volume, mute: .unmuted)
        let monitor = ScriptedMonitor(
            readResult: .success(initial),
            muteResults: [.success(.muted)]
        )
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )
        _ = await service.refresh()

        await service.enqueueMute(.muted)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: volume, mute: .muted)))
        #expect(await monitor.recordedOperations() == [.read, .writeMute(.muted)])
    }

    @Test
    func confirmsHardwareUnmuteWithoutChangingVolume() async throws {
        let volume = try #require(VolumeLevel(60))
        let initial = ConfirmedMonitorState(volume: volume, mute: .muted)
        let monitor = ScriptedMonitor(
            readResult: .success(initial),
            muteResults: [.success(.unmuted)]
        )
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )
        _ = await service.refresh()

        await service.enqueueMute(.unmuted)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: volume, mute: .unmuted)))
        #expect(await monitor.recordedOperations() == [.read, .writeMute(.unmuted)])
    }

    @Test(arguments: [MonitorRepositoryError.writeFailure, .readBackMismatch])
    func commandFailurePreservesConfirmedState(_ error: MonitorRepositoryError) async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let requested = try #require(VolumeLevel(65))
        let monitor = ScriptedMonitor(
            readResult: .success(initial),
            volumeResults: [.failure(error)]
        )
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )
        _ = await service.refresh()

        await service.enqueueVolume(requested)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .commandFailure(output: .active, state: initial, error: error))
    }

    @Test
    func coalescesPendingVolumeToLatestIntent() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let first = try #require(VolumeLevel(10))
        let superseded = try #require(VolumeLevel(20))
        let latest = try #require(VolumeLevel(30))
        let monitor = ControlledMonitor(initial: initial)
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )
        _ = await service.refresh()

        await service.enqueueVolume(first)
        #expect(await monitor.nextStartedOperation() == .writeVolume(10))
        await service.enqueueVolume(superseded)
        await service.enqueueVolume(latest)
        #expect(await monitor.completeVolume(.success(first)))
        #expect(await monitor.nextStartedOperation() == .writeVolume(30))
        #expect(await monitor.completeVolume(.success(latest)))

        let snapshot = await service.waitForPendingCommands()
        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: latest, mute: .unmuted)))
        #expect(await monitor.recordedOperations() == [.read, .writeVolume(10), .writeVolume(30)])
    }

    @Test
    func serializesVolumeAndMuteWrites() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let volume = try #require(VolumeLevel(65))
        let queuedVolume = try #require(VolumeLevel(70))
        let monitor = ControlledMonitor(initial: initial)
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )
        _ = await service.refresh()

        await service.enqueueVolume(volume)
        #expect(await monitor.nextStartedOperation() == .writeVolume(65))
        await service.enqueueVolume(queuedVolume)
        await service.enqueueMute(.muted)
        #expect(await monitor.completeVolume(.success(volume)))
        #expect(await monitor.nextStartedOperation() == .writeVolume(70))
        #expect(await monitor.completeVolume(.success(queuedVolume)))
        #expect(await monitor.nextStartedOperation() == .writeMute(.muted))
        #expect(await monitor.completeMute(.success(.muted)))
        _ = await service.waitForPendingCommands()

        #expect(await monitor.maximumConcurrentWrites() == 1)
    }

    @Test
    func keepsLatestVolumeAfterAnInterveningMuteIntent() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let first = try #require(VolumeLevel(65))
        let superseded = try #require(VolumeLevel(70))
        let latest = try #require(VolumeLevel(75))
        let monitor = ControlledMonitor(initial: initial)
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )
        _ = await service.refresh()

        await service.enqueueVolume(first)
        #expect(await monitor.nextStartedOperation() == .writeVolume(65))
        await service.enqueueVolume(superseded)
        await service.enqueueMute(.muted)
        await service.enqueueVolume(latest)
        #expect(await monitor.completeVolume(.success(first)))
        #expect(await monitor.nextStartedOperation() == .writeMute(.muted))
        #expect(await monitor.completeMute(.success(.muted)))
        #expect(await monitor.nextStartedOperation() == .writeVolume(75))
        #expect(await monitor.completeVolume(.success(latest)))

        let snapshot = await service.waitForPendingCommands()
        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: latest, mute: .muted)))
        #expect(
            await monitor.recordedOperations()
                == [.read, .writeVolume(65), .writeMute(.muted), .writeVolume(75)]
        )
        #expect(await monitor.maximumConcurrentWrites() == 1)
    }

    @Test
    func refreshesBeforeACommandWithoutConfirmedState() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let requested = try #require(VolumeLevel(65))
        let monitor = ScriptedMonitor(
            readResult: .success(initial),
            volumeResults: [.success(requested)]
        )
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )

        await service.enqueueVolume(requested)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: requested, mute: .unmuted)))
        #expect(await monitor.recordedOperations() == [.read, .writeVolume(65)])
    }

    @Test
    func publishesUnavailableWhenRefreshBeforeCommandFindsNoTarget() async throws {
        let requested = try #require(VolumeLevel(65))
        let monitor = ScriptedMonitor(readResult: .success(nil))
        let service = VolumeControlService(
            monitor: monitor,
            activeOutput: CommandStubActiveOutputReader(result: .success(true))
        )

        await service.enqueueVolume(requested)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .unavailable)
        #expect(await monitor.recordedOperations() == [.read])
    }
}

private enum RecordedMonitorOperation: Equatable, Sendable {
    case read
    case writeVolume(Int)
    case writeMute(MuteState)
}

private actor ScriptedMonitor: MonitorControlling {
    private let readResult: Result<ConfirmedMonitorState?, MonitorRepositoryError>
    private var volumeResults: [Result<VolumeLevel, MonitorRepositoryError>]
    private var muteResults: [Result<MuteState, MonitorRepositoryError>]
    private var operations: [RecordedMonitorOperation] = []

    init(
        readResult: Result<ConfirmedMonitorState?, MonitorRepositoryError>,
        volumeResults: [Result<VolumeLevel, MonitorRepositoryError>] = [],
        muteResults: [Result<MuteState, MonitorRepositoryError>] = []
    ) {
        self.readResult = readResult
        self.volumeResults = volumeResults
        self.muteResults = muteResults
    }

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        operations.append(.read)
        return try resultValue(readResult)
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        operations.append(.writeVolume(volume.rawValue))
        return try resultValue(volumeResults.isEmpty ? .failure(.writeFailure) : volumeResults.removeFirst())
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        operations.append(.writeMute(mute))
        return try resultValue(muteResults.isEmpty ? .failure(.writeFailure) : muteResults.removeFirst())
    }

    func recordedOperations() -> [RecordedMonitorOperation] {
        operations
    }

    private func resultValue<T>(_ result: Result<T, MonitorRepositoryError>) throws(MonitorRepositoryError) -> T {
        switch result {
        case let .success(value):
            return value
        case let .failure(error):
            throw error
        }
    }
}

private actor ControlledMonitor: MonitorControlling {
    private let initial: ConfirmedMonitorState
    private var operations: [RecordedMonitorOperation] = []
    private var startedOperations: [RecordedMonitorOperation] = []
    private var startedWaiter: CheckedContinuation<RecordedMonitorOperation, Never>?
    private var volumeCompletion: CheckedContinuation<Result<VolumeLevel, MonitorRepositoryError>, Never>?
    private var muteCompletion: CheckedContinuation<Result<MuteState, MonitorRepositoryError>, Never>?
    private var concurrentWrites = 0
    private var maximumWrites = 0

    init(initial: ConfirmedMonitorState) {
        self.initial = initial
    }

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        operations.append(.read)
        return initial
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        let operation = RecordedMonitorOperation.writeVolume(volume.rawValue)
        begin(operation)
        let result = await withCheckedContinuation { continuation in
            volumeCompletion = continuation
        }
        concurrentWrites -= 1
        return try resultValue(result)
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        let operation = RecordedMonitorOperation.writeMute(mute)
        begin(operation)
        let result = await withCheckedContinuation { continuation in
            muteCompletion = continuation
        }
        concurrentWrites -= 1
        return try resultValue(result)
    }

    func nextStartedOperation() async -> RecordedMonitorOperation {
        if !startedOperations.isEmpty {
            return startedOperations.removeFirst()
        }
        return await withCheckedContinuation { continuation in
            startedWaiter = continuation
        }
    }

    func completeVolume(_ result: Result<VolumeLevel, MonitorRepositoryError>) -> Bool {
        guard let continuation = volumeCompletion else {
            return false
        }
        volumeCompletion = nil
        continuation.resume(returning: result)
        return true
    }

    func completeMute(_ result: Result<MuteState, MonitorRepositoryError>) -> Bool {
        guard let continuation = muteCompletion else {
            return false
        }
        muteCompletion = nil
        continuation.resume(returning: result)
        return true
    }

    func recordedOperations() -> [RecordedMonitorOperation] {
        operations
    }

    func maximumConcurrentWrites() -> Int {
        maximumWrites
    }

    private func begin(_ operation: RecordedMonitorOperation) {
        operations.append(operation)
        concurrentWrites += 1
        maximumWrites = max(maximumWrites, concurrentWrites)
        if let waiter = startedWaiter {
            startedWaiter = nil
            waiter.resume(returning: operation)
        } else {
            startedOperations.append(operation)
        }
    }

    private func resultValue<T>(_ result: Result<T, MonitorRepositoryError>) throws(MonitorRepositoryError) -> T {
        switch result {
        case let .success(value):
            return value
        case let .failure(error):
            throw error
        }
    }
}

private struct CommandStubActiveOutputReader: ActiveAudioOutputReading {
    let result: Result<Bool, MonitorRepositoryError>

    func isTargetActive() async throws(MonitorRepositoryError) -> Bool {
        switch result {
        case let .success(value):
            return value
        case let .failure(error):
            throw error
        }
    }
}
