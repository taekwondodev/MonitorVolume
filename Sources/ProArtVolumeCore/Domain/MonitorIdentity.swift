package struct MonitorIdentity: Equatable, Sendable {
    package static let target = MonitorIdentity(
        manufacturer: "AUS",
        productID: 10_088,
        serial: "R5LMTF117048"
    )

    package let manufacturer: String
    package let productID: UInt32
    package let serial: String

    package func matches(manufacturer: String, productID: UInt32, serial: String) -> Bool {
        self.manufacturer == manufacturer && self.productID == productID && self.serial == serial
    }
}
