/// The cadence of a held button: one tick after the initial delay, then one per interval.
enum RepeatTicks {
    static let initialDelay = Duration.milliseconds(300)
    static let interval = Duration.milliseconds(100)

    static func holdToRepeat() -> AsyncStream<Void> {
        let (ticks, continuation) = AsyncStream.makeStream(of: Void.self)
        let timer = Task {
            var delay = initialDelay
            while true {
                do {
                    try await Task.sleep(for: delay)
                } catch {
                    break
                }
                continuation.yield()
                delay = interval
            }
            continuation.finish()
        }
        continuation.onTermination = { _ in timer.cancel() }
        return ticks
    }
}
