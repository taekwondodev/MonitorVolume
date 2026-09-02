import Testing
@testable import ProArtVolumeCore

@Suite
struct VolumeControlServiceTests {
    @Test
    func publishesConfirmedActiveState() async throws {
        let confirmedState = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(confirmedState)),
            activeOutput: StubActiveOutputReader(result: .success(true))
        )

        #expect(await service.refresh() == .confirmed(output: .active, state: confirmedState))
    }

    @Test
    func publishesConfirmedInactiveState() async throws {
        let confirmedState = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(confirmedState)),
            activeOutput: StubActiveOutputReader(result: .success(false))
        )

        #expect(await service.refresh() == .confirmed(output: .inactive, state: confirmedState))
    }

    @Test
    func keepsUnavailableDistinct() async {
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(nil)),
            activeOutput: StubActiveOutputReader(result: .success(true))
        )

        #expect(await service.refresh() == .unavailable)
    }

    @Test(arguments: [MonitorRepositoryError.malformedResponse, .readFailure])
    func mapsRepositoryFailures(_ error: MonitorRepositoryError) async {
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .failure(error)),
            activeOutput: StubActiveOutputReader(result: .success(true))
        )

        #expect(await service.refresh() == .failure(error))
    }

    @Test
    func mapsActiveOutputReadFailureSafely() async throws {
        let confirmedState = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(confirmedState)),
            activeOutput: StubActiveOutputReader(result: .failure(.readFailure))
        )

        #expect(await service.refresh() == .failure(.readFailure))
    }
}

private struct StubMonitorReader: MonitorStateReading {
    let result: Result<ConfirmedMonitorState?, MonitorRepositoryError>

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        try result.get()
    }
}

private struct StubActiveOutputReader: ActiveAudioOutputReading {
    let result: Result<Bool, MonitorRepositoryError>

    func isTargetActive() async throws(MonitorRepositoryError) -> Bool {
        try result.get()
    }
}
