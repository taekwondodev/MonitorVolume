import Testing
@testable import ProArtVolumeCore

@Suite
struct MonitorIdentityTests {
    @Test
    func targetRequiresEveryStableField() {
        let target = MonitorIdentity.target

        #expect(target.matches(manufacturer: "AUS", productID: 10_088, serial: "R5LMTF117048"))
        #expect(!target.matches(manufacturer: "DEL", productID: 10_088, serial: "R5LMTF117048"))
        #expect(!target.matches(manufacturer: "AUS", productID: 10_089, serial: "R5LMTF117048"))
        #expect(!target.matches(manufacturer: "AUS", productID: 10_088, serial: "OTHER"))
    }
}
