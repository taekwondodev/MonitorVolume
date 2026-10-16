import MonitorRemoteProtocol
import Testing
@testable import MonitorRemote

@MainActor
struct RemoteControllerTests {
    private let link = RecordingLink()
    private let ticks = ManualTicks()
    private let controller: RemoteController

    init() {
        controller = RemoteController(link: link, repeatTicks: ticks.makeStream)
    }

    @Test(arguments: [
        (RemoteLinkObservation(isConnected: true, isLocalNetworkDenied: false, isOnWiFi: true), RemoteStatus.connected, "Connected"),
        (RemoteLinkObservation(isConnected: false, isLocalNetworkDenied: true, isOnWiFi: true), .localNetworkDenied, "Local Network access denied"),
        (RemoteLinkObservation(isConnected: false, isLocalNetworkDenied: true, isOnWiFi: false), .localNetworkDenied, "Local Network access denied"),
        (RemoteLinkObservation(isConnected: false, isLocalNetworkDenied: false, isOnWiFi: false), .notOnWiFi, "iPhone not on Wi-Fi"),
        (RemoteLinkObservation(isConnected: false, isLocalNetworkDenied: false, isOnWiFi: true), .noMacFound, "No Mac found"),
    ])
    func observationMapsToStatusLabel(observation: RemoteLinkObservation, status: RemoteStatus, label: String) {
        controller.start()
        link.emit(observation)

        #expect(controller.status == status)
        #expect(String(localized: controller.status.label) == label)
    }

    @Test
    func buttonsAreEnabledOnlyWhileConnected() {
        controller.start()
        #expect(controller.isEnabled == false)

        controller.press(.volumeUp)
        #expect(link.sent.isEmpty)

        link.emit(.connected)
        #expect(controller.isEnabled)

        link.emit(RemoteLinkObservation(isConnected: false, isLocalNetworkDenied: false, isOnWiFi: false))
        #expect(controller.isEnabled == false)
    }

    @Test
    func holdSendsDownThenRepeatedDownsThenUp() async throws {
        controller.start()
        link.emit(.connected)
        var sent = link.commands.makeAsyncIterator()

        controller.press(.volumeDown)
        #expect(await sent.next() == RemoteCommand(key: .volumeDown, phase: .down))
        ticks.tick()
        #expect(await sent.next() == RemoteCommand(key: .volumeDown, phase: .down))
        ticks.tick()
        #expect(await sent.next() == RemoteCommand(key: .volumeDown, phase: .down))
        controller.release(.volumeDown)
        #expect(await sent.next() == RemoteCommand(key: .volumeDown, phase: .up))

        #expect(controller.sentPresses == 3)
    }

    @Test
    func backgroundReleasesEveryHeldKey() {
        controller.start()
        link.emit(.connected)
        controller.press(.volumeUp)
        controller.press(.mute)

        controller.enterBackground()

        #expect(link.sent == [
            RemoteCommand(key: .volumeUp, phase: .down),
            RemoteCommand(key: .mute, phase: .down),
            RemoteCommand(key: .volumeUp, phase: .up),
            RemoteCommand(key: .mute, phase: .up),
        ])
        #expect(link.isRunning == false)
        #expect(controller.isEnabled == false)
    }

    @Test
    func disconnectForgetsHeldKeysSoReleaseSendsNothing() {
        controller.start()
        link.emit(.connected)
        controller.press(.volumeUp)

        link.emit(RemoteLinkObservation())
        controller.release(.volumeUp)
        link.emit(.connected)
        controller.press(.volumeUp)

        #expect(link.sent == [
            RemoteCommand(key: .volumeUp, phase: .down),
            RemoteCommand(key: .volumeUp, phase: .down),
        ])
    }
}

private extension RemoteLinkObservation {
    static let connected = RemoteLinkObservation(isConnected: true, isLocalNetworkDenied: false, isOnWiFi: true)
}

@MainActor
private final class RecordingLink: RemoteLink {
    private(set) var sent: [RemoteCommand] = []
    private(set) var isRunning = false
    let commands: AsyncStream<RemoteCommand>
    private let continuation: AsyncStream<RemoteCommand>.Continuation
    private var observer: (@MainActor (RemoteLinkObservation) -> Void)?

    init() {
        (commands, continuation) = AsyncStream.makeStream(of: RemoteCommand.self)
    }

    func start(observing observer: @escaping @MainActor (RemoteLinkObservation) -> Void) {
        isRunning = true
        self.observer = observer
    }

    func stop() {
        isRunning = false
        observer = nil
    }

    func send(_ command: RemoteCommand) {
        sent.append(command)
        continuation.yield(command)
    }

    func emit(_ observation: RemoteLinkObservation) {
        observer?(observation)
    }
}

/// Repeat ticks the test delivers by hand; unconsumed ticks stay buffered.
@MainActor
private final class ManualTicks {
    private var continuations: [AsyncStream<Void>.Continuation] = []

    func makeStream() -> AsyncStream<Void> {
        let (stream, continuation) = AsyncStream.makeStream(of: Void.self)
        continuations.append(continuation)
        return stream
    }

    func tick() {
        for continuation in continuations {
            continuation.yield()
        }
    }
}
