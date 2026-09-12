package struct MonitorIdentity: Equatable, Hashable, Sendable {
    package let manufacturer: String
    package let productID: UInt32
    package let serial: String?

    package init(manufacturer: String, productID: UInt32, serial: String?) {
        self.manufacturer = manufacturer
        self.productID = productID
        self.serial = serial
    }
}
