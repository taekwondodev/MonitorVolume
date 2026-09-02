import Testing
@testable import ProArtVolumeCore

@Suite
struct MuteStateTests {
    @Test
    func mapsConfirmedHardwareValues() throws {
        #expect(try MuteState(hardwareValue: 1) == .muted)
        #expect(try MuteState(hardwareValue: 2) == .unmuted)
    }

    @Test
    func rejectsUnsupportedHardwareValue() {
        #expect(throws: MonitorRepositoryError.malformedResponse) {
            try MuteState(hardwareValue: 0)
        }
    }
}
