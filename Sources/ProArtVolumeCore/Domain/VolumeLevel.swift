package struct VolumeLevel: Equatable, Sendable {
    package let rawValue: Int

    package init?(_ rawValue: Int) {
        guard (0...100).contains(rawValue) else {
            return nil
        }
        self.rawValue = rawValue
    }


    package func adjusting(by points: Int) -> VolumeLevel {
        VolumeLevel(clamping: rawValue + min(100, max(-100, points)))
    }

    private init(clamping rawValue: Int) {
        self.rawValue = min(100, max(0, rawValue))
    }
}
