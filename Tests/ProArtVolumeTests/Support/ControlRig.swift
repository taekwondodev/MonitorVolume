import Testing
@testable import ProArtVolumeCore

struct ControlRig {
    let eligibility = ControlEligibility()
    let monitor: IntentTestMonitor
    let output = IntentTestOutput()
    let timer = IntentTestTimer()
    let service: IntentControlService

    init(volume: Int, mute: MuteState = .unmuted) throws {
        monitor = IntentTestMonitor(state: .init(volume: try #require(VolumeLevel(volume)), mute: mute))
        let timer = timer
        service = IntentControlService(monitor: monitor, activeOutput: output, eligibility: eligibility,
                                       sleeper: ControlSleeper { await timer.sleep($0) })
    }

    func start() async {
        await service.revalidate(generation: eligibility.invalidate(), permitted: true)
        await service.waitForIdle()
    }
}

actor IntentTestOutput: ActiveAudioOutputReading {
    private var active = true
    func setActive(_ value: Bool) { active = value }
    func isTargetActive() async throws(MonitorRepositoryError) -> Bool { active }
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

actor IntentTestMonitor: MonitorControlling {
    private var state: ConfirmedMonitorState
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
    private(set) var writtenVolumes: [Int] = []
    private(set) var writtenMutes: [MuteState] = []
    private(set) var readCount = 0

    init(state: ConfirmedMonitorState) { self.state = state }
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

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
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
        return readable ? state : nil
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        begin()
        defer { operations -= 1 }
        writtenVolumes.append(volume.rawValue)
        if hold {
            hold = false
            await withCheckedContinuation { continuation in
                held = continuation
                started?.resume()
                started = nil
            }
        }
        if let error = writeError { writeError = nil; throw error }
        state = .init(volume: volume, mute: state.mute)
        return volume
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        begin()
        defer { operations -= 1 }
        writtenMutes.append(mute)
        if muteFailure { muteFailure = false; throw .writeFailure }
        state = .init(volume: state.volume, mute: mute)
        return mute
    }
}
