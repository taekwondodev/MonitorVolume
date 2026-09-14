package struct RecoveryDelay: Sendable {
    private var attempt = 0

    package init() {}

    package mutating func next() -> Duration {
        let seconds = [2, 5, 10, 30][attempt]
        attempt = min(attempt + 1, 3)
        return .seconds(seconds)
    }
}

package struct ControlSleeper: Sendable {
    private let body: @Sendable (Duration) async throws -> Void

    package init(_ body: @escaping @Sendable (Duration) async throws -> Void) {
        self.body = body
    }

    package func sleep(for delay: Duration) async throws {
        try await body(delay)
    }

    package static let continuous = Self { try await Task.sleep(for: $0) }
}
