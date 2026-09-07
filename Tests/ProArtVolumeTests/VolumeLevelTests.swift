import Testing
@testable import ProArtVolumeCore

struct VolumeLevelTests {
    @Test
    func acceptsHardwareBounds() {
        #expect(VolumeLevel(0)?.rawValue == 0)
        #expect(VolumeLevel(100)?.rawValue == 100)
    }

    @Test
    func rejectsValuesOutsideHardwareRange() {
        #expect(VolumeLevel(-1) == nil)
        #expect(VolumeLevel(101) == nil)
    }


}
