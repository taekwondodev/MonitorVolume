import Synchronization

final class MediaKeyRoutingSnapshot: Sendable {
    private let targetIsActive = Mutex(false)

    func read() -> Bool {
        targetIsActive.withLock { $0 }
    }

    func update(_ isActive: Bool) {
        targetIsActive.withLock { $0 = isActive }
    }
}
