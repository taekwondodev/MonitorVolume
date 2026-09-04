import Testing
@testable import ProArtVolumeCore

struct MediaKeyCommandServiceTests {
    @Test
    func activeVolumeStepReadsHardwareAndConfirmsFivePointIncrease() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(50)), mute: .unmuted)
        let confirmed = try #require(VolumeLevel(55))
        let monitor = MediaScriptedMonitor(states: [initial], volumeResults: [.success(confirmed)])
        let output = MediaActiveOutputReader(values: [true])
        let service = VolumeControlService(monitor: monitor, activeOutput: output)

        await service.enqueueVolumeStep(.increase)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: confirmed, mute: .unmuted)))
        #expect(await monitor.operations == [.read, .writeVolume(55)])
    }

    @Test
    func volumeStepUnmutesHardwareInTheSameConfirmedCommand() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(50)), mute: .muted)
        let confirmed = try #require(VolumeLevel(55))
        let monitor = MediaScriptedMonitor(
            states: [initial],
            volumeResults: [.success(confirmed)],
            muteResults: [.success(.unmuted)]
        )
        let output = MediaActiveOutputReader(values: [true])
        let service = VolumeControlService(monitor: monitor, activeOutput: output)

        await service.enqueueVolumeStep(.increase)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: confirmed, mute: .unmuted)))
        #expect(await monitor.operations == [.read, .writeVolume(55), .writeMute(.unmuted)])
    }

    @Test
    func inactiveTargetPassesWithoutAnyDDCCall() async {
        let monitor = MediaScriptedMonitor(states: [])
        let output = MediaActiveOutputReader(values: [false])
        let service = VolumeControlService(monitor: monitor, activeOutput: output)

        await service.enqueueVolumeStep(.increase)
        _ = await service.waitForPendingCommands()

        #expect(await output.readCount == 1)
        #expect(await monitor.operations.isEmpty)
    }

    @Test
    func rapidStepsAggregateAndNeverOverlapDDCWrites() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(50)), mute: .unmuted)
        let monitor = MediaControlledMonitor(initial: initial)
        let output = MediaActiveOutputReader(values: [true, true])
        let service = VolumeControlService(monitor: monitor, activeOutput: output)

        await service.enqueueVolumeStep(.increase)
        #expect(await monitor.nextWrite() == 55)
        await service.enqueueVolumeStep(.increase)
        await service.enqueueVolumeStep(.increase)
        #expect(await monitor.completeWrite())
        #expect(await monitor.nextWrite() == 65)
        #expect(await monitor.completeWrite())

        let snapshot = await service.waitForPendingCommands()
        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: try #require(VolumeLevel(65)), mute: .unmuted)))
        #expect(await monitor.maximumConcurrentWrites == 1)
    }

    @Test
    func aggregatesOnlyAdjacentVolumeSteps() async throws {
        let initial = ConfirmedMonitorState(volume: try #require(VolumeLevel(50)), mute: .unmuted)
        let monitor = MediaRecordingMonitor(initial: initial)
        let output = MediaGatedActiveOutputReader()
        let service = VolumeControlService(monitor: monitor, activeOutput: output)

        await service.enqueueVolumeStep(.increase)
        await output.waitUntilReadStarts()
        await service.enqueueVolumeStep(.increase)
        await service.enqueueVolumeStep(.increase)
        await service.enqueueMuteToggle()
        await service.enqueueVolumeStep(.increase)
        await output.resumeRead()
        _ = await service.waitForPendingCommands()

        #expect(
            await monitor.operations
                == [
                    .read,
                    .writeVolume(55),
                    .read,
                    .writeVolume(65),
                    .read,
                    .writeMute(.muted),
                    .read,
                    .writeVolume(70),
                    .writeMute(.unmuted),
                ]
        )
    }

    @Test
    func cancelledIntentDoesNotReachTheRepositories() async {
        let gate = MediaCommandGate()
        let monitor = MediaScriptedMonitor(states: [])
        let output = MediaActiveOutputReader(values: [true])
        let service = VolumeControlService(monitor: monitor, activeOutput: output)
        let task = Task {
            await gate.wait()
            await service.enqueueVolumeStep(.increase)
        }

        task.cancel()
        await gate.open()
        await task.value
        _ = await service.waitForPendingCommands()

        #expect(await output.readCount == 0)
        #expect(await monitor.operations.isEmpty)
    }

    @Test
    func activeMuteKeyTogglesHardwareMute() async throws {
        let volume = try #require(VolumeLevel(50))
        let initial = ConfirmedMonitorState(volume: volume, mute: .unmuted)
        let monitor = MediaScriptedMonitor(states: [initial], muteResults: [.success(.muted)])
        let output = MediaActiveOutputReader(values: [true])
        let service = VolumeControlService(monitor: monitor, activeOutput: output)

        await service.enqueueMuteToggle()
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .confirmed(output: .active, state: .init(volume: volume, mute: .muted)))
        #expect(await monitor.operations == [.read, .writeMute(.muted)])
    }

    @Test
    func writeFailurePreservesFreshActiveHardwareState() async throws {
        let fresh = ConfirmedMonitorState(volume: try #require(VolumeLevel(50)), mute: .unmuted)
        let monitor = MediaScriptedMonitor(states: [fresh], volumeResults: [.failure(.writeFailure)])
        let output = MediaActiveOutputReader(values: [true])
        let service = VolumeControlService(monitor: monitor, activeOutput: output)

        await service.enqueueVolumeStep(.increase)
        let snapshot = await service.waitForPendingCommands()

        #expect(snapshot.status == .commandFailure(output: .active, state: fresh, error: .writeFailure))
    }
}

private enum MediaMonitorOperation: Equatable, Sendable {
    case read
    case writeVolume(Int)
    case writeMute(MuteState)
}

private actor MediaScriptedMonitor: MonitorControlling {
    private var states: [ConfirmedMonitorState]
    private var volumeResults: [Result<VolumeLevel, MonitorRepositoryError>]
    private var muteResults: [Result<MuteState, MonitorRepositoryError>]
    private(set) var operations: [MediaMonitorOperation] = []

    init(
        states: [ConfirmedMonitorState],
        volumeResults: [Result<VolumeLevel, MonitorRepositoryError>] = [],
        muteResults: [Result<MuteState, MonitorRepositoryError>] = []
    ) {
        self.states = states
        self.volumeResults = volumeResults
        self.muteResults = muteResults
    }

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        operations.append(.read)
        return states.isEmpty ? nil : states.removeFirst()
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        operations.append(.writeVolume(volume.rawValue))
        return try value(from: volumeResults.removeFirst())
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        operations.append(.writeMute(mute))
        return try value(from: muteResults.removeFirst())
    }

    private func value<T>(from result: Result<T, MonitorRepositoryError>) throws(MonitorRepositoryError) -> T {
        switch result {
        case let .success(value):
            return value
        case let .failure(error):
            throw error
        }
    }
}

private actor MediaActiveOutputReader: ActiveAudioOutputReading {
    private var values: [Bool]
    private(set) var readCount = 0

    init(values: [Bool]) {
        self.values = values
    }

    func isTargetActive() async throws(MonitorRepositoryError) -> Bool {
        readCount += 1
        return values.removeFirst()
    }
}

private actor MediaGatedActiveOutputReader: ActiveAudioOutputReading {
    private var readContinuation: CheckedContinuation<Void, Never>?
    private var readStartedContinuation: CheckedContinuation<Void, Never>?
    private var hasStartedRead = false
    private var shouldWait = true

    func isTargetActive() async throws(MonitorRepositoryError) -> Bool {
        if shouldWait {
            hasStartedRead = true
            readStartedContinuation?.resume()
            readStartedContinuation = nil
            await withCheckedContinuation { continuation in
                readContinuation = continuation
            }
            shouldWait = false
        }
        return true
    }

    func waitUntilReadStarts() async {
        guard !hasStartedRead else {
            return
        }
        await withCheckedContinuation { continuation in
            readStartedContinuation = continuation
        }
    }

    func resumeRead() {
        readContinuation?.resume()
        readContinuation = nil
    }
}

private actor MediaRecordingMonitor: MonitorControlling {
    private var state: ConfirmedMonitorState
    private(set) var operations: [MediaMonitorOperation] = []

    init(initial: ConfirmedMonitorState) {
        state = initial
    }

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        operations.append(.read)
        return state
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        operations.append(.writeVolume(volume.rawValue))
        state = ConfirmedMonitorState(volume: volume, mute: state.mute)
        return volume
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        operations.append(.writeMute(mute))
        state = ConfirmedMonitorState(volume: state.volume, mute: mute)
        return mute
    }
}

private actor MediaControlledMonitor: MonitorControlling {
    private var state: ConfirmedMonitorState
    private var writeContinuation: CheckedContinuation<Void, Never>?
    private var pendingVolume: VolumeLevel?
    private var startedWrites: [Int] = []
    private var startedWaiter: CheckedContinuation<Int, Never>?
    private var concurrentWrites = 0
    private(set) var maximumConcurrentWrites = 0

    init(initial: ConfirmedMonitorState) {
        state = initial
    }

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        state
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        concurrentWrites += 1
        maximumConcurrentWrites = max(maximumConcurrentWrites, concurrentWrites)
        pendingVolume = volume
        if let startedWaiter {
            self.startedWaiter = nil
            startedWaiter.resume(returning: volume.rawValue)
        } else {
            startedWrites.append(volume.rawValue)
        }
        await withCheckedContinuation { continuation in
            writeContinuation = continuation
        }
        concurrentWrites -= 1
        state = ConfirmedMonitorState(volume: volume, mute: state.mute)
        return volume
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        throw .writeFailure
    }

    func nextWrite() async -> Int {
        if !startedWrites.isEmpty {
            return startedWrites.removeFirst()
        }
        return await withCheckedContinuation { continuation in
            startedWaiter = continuation
        }
    }

    func completeWrite() -> Bool {
        guard pendingVolume != nil, let writeContinuation else {
            return false
        }
        pendingVolume = nil
        self.writeContinuation = nil
        writeContinuation.resume()
        return true
    }
}

private actor MediaCommandGate {
    private var continuation: CheckedContinuation<Void, Never>?
    private var isOpen = false

    func wait() async {
        if isOpen {
            return
        }
        await withCheckedContinuation { continuation in
            self.continuation = continuation
        }
    }

    func open() {
        isOpen = true
        continuation?.resume()
        continuation = nil
    }
}
