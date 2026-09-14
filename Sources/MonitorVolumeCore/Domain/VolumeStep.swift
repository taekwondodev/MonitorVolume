package enum VolumeStep: Equatable, Sendable {
    case increase
    case decrease

    package var points: Int {
        switch self {
        case .increase:
            5
        case .decrease:
            -5
        }
    }
}
