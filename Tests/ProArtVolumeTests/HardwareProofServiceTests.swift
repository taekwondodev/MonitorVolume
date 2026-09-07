import Testing
@testable import ProArtVolumeCore

struct HardwareProofServiceTests {
    @Test(arguments: [(80, [81, 80]), (100, [99, 100])])
    func provesActualTransitionsAndRestores(volume: Int, expected: [Int]) async throws {
        let monitor = try ProofMonitor(volume: volume)
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput()).run()
        #expect(report.status == "passed")
        #expect(await monitor.volumes == expected)
        #expect(await monitor.mutes == [.muted, .unmuted])
        #expect(report.phases.count == 2)
        #expect(report.final.observed?.volume == volume)
        #expect(report.final.observed?.mute == "unmuted")
    }

    @Test func uncertainTransitionStillRestoresOnceAndContinuesDiagnostics() async throws {
        let monitor = try ProofMonitor(volume: 80, failingWrites: [1])
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput()).run()
        #expect(report.status == "failed")
        #expect(await monitor.volumes == [81, 80])
        #expect(report.phases.count == 2)
        #expect(report.phases[0].transition.confirmed == false)
        #expect(report.phases[0].restoration.confirmed)
        #expect(report.final.observed?.volume == 80)
    }

    @Test func unconfirmedRestorationStopsAllFurtherWrites() async throws {
        let monitor = try ProofMonitor(volume: 80, failingWrites: [2])
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput()).run()
        #expect(report.status == "failed")
        #expect(await monitor.volumes == [81, 80])
        #expect(await monitor.mutes.isEmpty)
        #expect(report.phases.count == 1)
        #expect(report.phases[0].restoration.confirmed == false)
        #expect(report.final.observed?.volume == 80)
    }

    @Test func unavailableInitialStateMakesNoWrites() async throws {
        let monitor = try ProofMonitor(volume: 80, available: false)
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput()).run()
        #expect(report.status == "failed")
        #expect(report.phases.isEmpty)
        #expect(await monitor.volumes.isEmpty)
        #expect(await monitor.mutes.isEmpty)
    }

    @Test(arguments: [3, 4])
    func muteFailureStillAttemptsExactlyOneRestoration(failure: Int) async throws {
        let monitor = try ProofMonitor(volume: 80, failingWrites: [failure])
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput()).run()
        #expect(report.status == "failed")
        #expect(await monitor.volumes == [81, 80])
        #expect(await monitor.mutes == [.muted, .unmuted])
        #expect(report.phases.count == 2)
        #expect(report.phases[1].transition.confirmed == (failure != 3))
        #expect(report.phases[1].restoration.confirmed == (failure != 4))
        #expect(report.phases[1].restoration.writeAttempted)
    }

    @Test func outputLossRefusesRestorationButStillCapturesFinalState() async throws {
        let monitor = try ProofMonitor(volume: 80)
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput(activeForCalls: 2)).run()
        #expect(report.status == "failed")
        #expect(await monitor.volumes == [81])
        #expect(await monitor.mutes.isEmpty)
        #expect(report.phases[0].restoration.writeAttempted == false)
        #expect(report.phases[0].restoration.error == "inactive_output")
        #expect(report.final.observed?.volume == 81)
        #expect(report.final.writeAttempted == false)
    }

    @Test func inactiveInitialOutputMakesNoHardwareCalls() async throws {
        let monitor = try ProofMonitor(volume: 80)
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput(activeForCalls: 0)).run()
        #expect(report.status == "failed")
        #expect(report.phases.isEmpty)
        #expect(await monitor.readCount == 0)
        #expect(await monitor.volumes.isEmpty)
        #expect(await monitor.mutes.isEmpty)
    }

    @Test func finalReadFailureCannotPassRestoredPhases() async throws {
        let monitor = try ProofMonitor(volume: 80, failingReads: [6])
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput()).run()
        #expect(report.status == "failed")
        #expect(report.phases.allSatisfy { $0.transition.confirmed && $0.restoration.confirmed })
        #expect(report.final.error == "readFailure")
        #expect(report.final.observed == nil)
        #expect(await monitor.volumes == [81, 80])
        #expect(await monitor.mutes == [.muted, .unmuted])
    }

    @Test func mismatchingTransitionIsFailedEvenAfterRestoration() async throws {
        let monitor = try ProofMonitor(volume: 80, mismatchingReads: [2])
        let report = await HardwareProofService(monitor: monitor, output: ProofOutput()).run()
        #expect(report.status == "failed")
        #expect(report.phases[0].transition.error == "readBackMismatch")
        #expect(report.phases[0].restoration.confirmed)
        #expect(report.phases.count == 2)
        #expect(await monitor.volumes == [81, 80])
    }

    @Test func singleUsePreventsConcurrentProofWriters() async throws {
        let monitor = try ProofMonitor(volume: 80)
        let service = HardwareProofService(monitor: monitor, output: ProofOutput())
        async let first = service.run()
        async let second = service.run()
        let results = await [first, second]
        #expect(results.filter { $0.status == "passed" }.count == 1)
        #expect(await monitor.volumes == [81, 80])
    }
}

private actor ProofOutput: ActiveAudioOutputReading {
    private var remaining: Int
    init(activeForCalls: Int = .max) { remaining = activeForCalls }
    func isTargetActive() async throws(MonitorRepositoryError) -> Bool {
        guard remaining > 0 else { return false }
        remaining -= 1
        return true
    }
}

private actor ProofMonitor: MonitorControlling {
    private var state: ConfirmedMonitorState
    private let available: Bool
    private let failingWrites: Set<Int>
    private let failingReads: Set<Int>
    private let mismatchingReads: Set<Int>
    private var writes = 0
    private(set) var readCount = 0
    private(set) var volumes: [Int] = []
    private(set) var mutes: [MuteState] = []

    init(volume: Int, available: Bool = true, failingWrites: Set<Int> = [],
         failingReads: Set<Int> = [], mismatchingReads: Set<Int> = []) throws {
        state = .init(volume: try #require(VolumeLevel(volume)), mute: .unmuted)
        self.available = available
        self.failingWrites = failingWrites
        self.failingReads = failingReads
        self.mismatchingReads = mismatchingReads
    }

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        readCount += 1
        if failingReads.contains(readCount) { throw .readFailure }
        if mismatchingReads.contains(readCount) {
            return .init(volume: state.volume, mute: state.mute.toggled)
        }
        return available ? state : nil
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        volumes.append(volume.rawValue)
        state = .init(volume: volume, mute: state.mute)
        writes += 1
        if failingWrites.contains(writes) { throw .readFailure }
        return volume
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        mutes.append(mute)
        state = .init(volume: state.volume, mute: mute)
        writes += 1
        if failingWrites.contains(writes) { throw .readFailure }
        return mute
    }
}
