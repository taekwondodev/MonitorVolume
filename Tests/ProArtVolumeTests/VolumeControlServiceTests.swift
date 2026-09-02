import Testing
@testable import ProArtVolumeCore

struct VolumeControlServiceTests {
    @Test
    func publishesConfirmedActiveState() async throws {
        let confirmedState = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(confirmedState)),
            activeOutput: StubActiveOutputReader(result: .success(true))
        )

        #expect(await service.refresh().status == .confirmed(output: .active, state: confirmedState))
    }

    @Test
    func publishesConfirmedInactiveState() async throws {
        let confirmedState = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(confirmedState)),
            activeOutput: StubActiveOutputReader(result: .success(false))
        )

        #expect(await service.refresh().status == .confirmed(output: .inactive, state: confirmedState))
    }

    @Test
    func keepsUnavailableDistinct() async {
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(nil)),
            activeOutput: StubActiveOutputReader(result: .success(true))
        )

        #expect(await service.refresh().status == .unavailable)
    }

    @Test(arguments: [MonitorRepositoryError.malformedResponse, .readFailure])
    func mapsRepositoryFailures(_ error: MonitorRepositoryError) async {
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .failure(error)),
            activeOutput: StubActiveOutputReader(result: .success(true))
        )

        #expect(await service.refresh().status == .failure(error))
    }

    @Test
    func mapsActiveOutputReadFailureSafely() async throws {
        let confirmedState = ConfirmedMonitorState(volume: try #require(VolumeLevel(60)), mute: .unmuted)
        let service = VolumeControlService(
            monitor: StubMonitorReader(result: .success(confirmedState)),
            activeOutput: StubActiveOutputReader(result: .failure(.readFailure))
        )

        #expect(await service.refresh().status == .failure(.readFailure))
    }
}

private struct StubMonitorReader: MonitorControlling {
    let result: Result<ConfirmedMonitorState?, MonitorRepositoryError>

    func readState() async throws(MonitorRepositoryError) -> ConfirmedMonitorState? {
        try result.get()
    }

    func writeVolume(_ volume: VolumeLevel) async throws(MonitorRepositoryError) -> VolumeLevel {
        throw .writeFailure
    }

    func writeMute(_ mute: MuteState) async throws(MonitorRepositoryError) -> MuteState {
        throw .writeFailure
    }
}

private struct StubActiveOutputReader: ActiveAudioOutputReading {
    let result: Result<Bool, MonitorRepositoryError>

    func isTargetActive() async throws(MonitorRepositoryError) -> Bool {
        try result.get()
    }
}
