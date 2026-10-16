import MonitorRemoteProtocol
import Observation

/// Turns button presses into remote commands while the Mac is connected.
@MainActor
@Observable
final class RemoteController {
    private(set) var status = RemoteStatus.noMacFound
    /// Counts sent key-downs, including repeats; drives the send haptic.
    private(set) var sentPresses = 0

    var isEnabled: Bool { status == .connected }

    @ObservationIgnored private let link: any RemoteLink
    @ObservationIgnored private let repeatTicks: @MainActor () -> AsyncStream<Void>
    @ObservationIgnored private var heldKeys: [RemoteKey: Task<Void, Never>] = [:]
    @ObservationIgnored private var isRunning = false

    init(link: any RemoteLink, repeatTicks: @escaping @MainActor () -> AsyncStream<Void> = RepeatTicks.holdToRepeat) {
        self.link = link
        self.repeatTicks = repeatTicks
    }

    func start() {
        guard isRunning == false else { return }
        isRunning = true
        link.start { [weak self] observation in
            self?.observe(observation)
        }
    }

    /// Releases every held key, then lets go of the Mac until the next start.
    func enterBackground() {
        releaseAll()
        isRunning = false
        link.stop()
        status = .noMacFound
    }

    func press(_ key: RemoteKey) {
        guard isEnabled, heldKeys[key] == nil else { return }
        sendDown(key)
        let ticks = repeatTicks()
        heldKeys[key] = Task { [weak self] in
            for await _ in ticks {
                guard Task.isCancelled == false, let self else { return }
                self.sendDown(key)
            }
        }
    }

    func release(_ key: RemoteKey) {
        guard let repeating = heldKeys.removeValue(forKey: key) else { return }
        repeating.cancel()
        link.send(RemoteCommand(key: key, phase: .up))
    }

    /// One press and release, for assistive activation without a hold.
    func tap(_ key: RemoteKey) {
        press(key)
        release(key)
    }

    private func releaseAll() {
        for key in RemoteKey.allCases {
            release(key)
        }
    }

    private func sendDown(_ key: RemoteKey) {
        link.send(RemoteCommand(key: key, phase: .down))
        sentPresses += 1
    }

    private func observe(_ observation: RemoteLinkObservation) {
        status = RemoteStatus(observation)
        guard isEnabled == false else { return }
        // The Mac releases a lost connection's held keys itself.
        for repeating in heldKeys.values {
            repeating.cancel()
        }
        heldKeys.removeAll()
    }
}
