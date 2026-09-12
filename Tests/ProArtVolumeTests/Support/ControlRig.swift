import Testing
@testable import ProArtVolumeCore

struct ControlRig {
    let eligibility = ControlEligibility()
    let monitor: IntentTestMonitor
    let output: IntentTestOutput
    let timer = IntentTestTimer()
    let service: IntentControlService

    init(volume: Int, mute: MonitorMuteState = .unmuted) throws {
        let target = AudioDisplayTarget.fixture(name: "ASUS PA279CV", productID: 10_088)
        try self.init(
            targets: [target: .fixture(volume: volume, mute: mute)],
            selected: target
        )
    }

    init(targets: [AudioDisplayTarget: ConfirmedMonitorState], selected: AudioDisplayTarget) throws {
        monitor = IntentTestMonitor(states: Dictionary(uniqueKeysWithValues: targets.map { ($0.key.identity, $0.value) }))
        output = IntentTestOutput(target: selected)
        let timer = timer
        service = IntentControlService(
            monitor: monitor,
            activeOutput: output,
            eligibility: eligibility,
            sleeper: ControlSleeper { await timer.sleep($0) }
        )
    }

    func start() async {
        await revalidate()
    }

    func revalidate() async {
        await service.revalidate(generation: eligibility.invalidate(), permitted: true)
        await service.waitForIdle()
    }
}

actor IntentTestOutput: ActiveAudioOutputReading {
    private let availableTarget: AudioDisplayTarget?
    private var target: AudioDisplayTarget?

    init(target: AudioDisplayTarget? = .fixture(name: "ASUS PA279CV", productID: 10_088)) {
        availableTarget = target
        self.target = target
    }

    func setActive(_ value: Bool) {
        target = value ? availableTarget : nil
    }

    func select(_ target: AudioDisplayTarget?) {
        self.target = target
    }

    func resolveTarget() async throws(MonitorRepositoryError) -> AudioDisplayTarget? {
        target
    }
}

actor IntentTestTimer {
    private var delay: Duration?
    private var sleeper: CheckedContinuation<Void, Never>?
    private var delayWaiter: CheckedContinuation<Duration, Never>?
    private(set) var requestCount = 0

    func sleep(_ duration: Duration) async {
        requestCount += 1
        delay = duration
        await withCheckedContinuation { continuation in
            sleeper = continuation
            delayWaiter?.resume(returning: duration)
            delayWaiter = nil
        }
    }

    func nextDelay() async -> Duration {
        if let delay { return delay }
        return await withCheckedContinuation { delayWaiter = $0 }
    }

    func advance() {
        delay = nil
        sleeper?.resume()
        sleeper = nil
    }
}

struct IntentTestVolumeWrite: Equatable, Sendable {
    let target: MonitorIdentity
    let value: Int
}

struct IntentTestMuteWrite: Equatable, Sendable {
    let target: MonitorIdentity
    let value: MuteState
}

actor IntentTestMonitor: MonitorControlling {
    private var states: [MonitorIdentity: ConfirmedMonitorState]
    private var readable = true
    private var readError: MonitorRepositoryError?
    private var holdRead = false
    private var heldRead: CheckedContinuation<Void, Never>?
    private var readStarted: CheckedContinuation<Void, Never>?
    private var muteFailure = false
    private var hold = false
    private var writeError: MonitorRepositoryError?
    private var held: CheckedContinuation<Void, Never>?
    private var started: CheckedContinuation<Void, Never>?
    private var operations = 0
    private(set) var maximumConcurrentOperations = 0
    private(set) var volumeWrites: [IntentTestVolumeWrite] = []
    private(set) var muteWrites: [IntentTestMuteWrite] = []
    private(set) var readCount = 0

    var writtenVolumes: [Int] { volumeWrites.map(\.value) }
    var writtenMutes: [MuteState] { muteWrites.map(\.value) }

    init(states: [MonitorIdentity: ConfirmedMonitorState]) {
        self.states = states
    }

    func setReadable(_ value: Bool) { readable = value }
    func failNextRead(_ error: MonitorRepositoryError) { readError = error }
    func holdNextRead() { holdRead = true }
    func waitForHeldRead() async {
        if heldRead != nil { return }
        await withCheckedContinuation { readStarted = $0 }
    }
    func releaseRead() { heldRead?.resume(); heldRead = nil }
    func failMute() { muteFailure = true }
    func holdNextWrite(error: MonitorRepositoryError? = nil) { hold = true; writeError = error }

    func waitForHeldWrite() async {
        if held != nil { return }
        await withCheckedContinuation { started = $0 }
    }

    func releaseWrite() { held?.resume(); held = nil }

    private func begin() { operations += 1; maximumConcurrentOperations = max(maximumConcurrentOperations, operations) }

    func readState(for target: MonitorIdentity) async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        begin()
        defer { operations -= 1 }
        readCount += 1
        if holdRead {
            holdRead = false
            await withCheckedContinuation { continuation in
                heldRead = continuation
                readStarted?.resume()
                readStarted = nil
            }
        }
        if let error = readError { readError = nil; throw error }
        return readable ? states[target] : nil
    }

    func writeVolume(
        _ volume: VolumeLevel,
        for target: MonitorIdentity
    ) async throws(MonitorRepositoryError) -> VolumeLevel {
        begin()
        defer { operations -= 1 }
        volumeWrites.append(.init(target: target, value: volume.rawValue))
        if hold {
            hold = false
            await withCheckedContinuation { continuation in
                held = continuation
                started?.resume()
                started = nil
            }
        }
        if let error = writeError { writeError = nil; throw error }
        guard let state = states[target] else { throw .writeFailure }
        states[target] = .init(volume: volume, mute: state.mute)
        return volume
    }

    func writeMute(
        _ mute: MuteState,
        for target: MonitorIdentity
    ) async throws(MonitorRepositoryError) -> MuteState {
        begin()
        defer { operations -= 1 }
        muteWrites.append(.init(target: target, value: mute))
        if muteFailure { muteFailure = false; throw .writeFailure }
        guard let state = states[target] else { throw .writeFailure }
        states[target] = .init(volume: state.volume, mute: .supported(mute))
        return mute
    }
}
