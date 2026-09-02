package struct VolumeLevel: Equatable, Sendable {
    package let rawValue: Int

    package init?(_ rawValue: Int) {
        guard (0...100).contains(rawValue) else {
            return nil
        }
        self.rawValue = rawValue
    }

    package init?(_ rawValue: Double) {
        guard rawValue.isFinite,
              rawValue.rounded() == rawValue,
              let integer = Int(exactly: rawValue) else {
            return nil
        }
        self.init(integer)
    }
}
