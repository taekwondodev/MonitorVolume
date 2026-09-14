import Testing
@testable import MonitorVolumeCore

struct MuteStateTests {
    @Test
    func mapsConfirmedHardwareValues() throws {
        #expect(try MuteState(hardwareValue: 1) == .muted)
        #expect(try MuteState(hardwareValue: 2) == .unmuted)
        #expect(MuteState.muted.hardwareValue == 1)
        #expect(MuteState.unmuted.hardwareValue == 2)
    }

    @Test
    func rejectsUnsupportedHardwareValue() {
        #expect(throws: MonitorRepositoryError.malformedResponse) {
            try MuteState(hardwareValue: 0)
        }
    }
}
