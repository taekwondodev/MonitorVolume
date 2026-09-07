package struct VolumeIntent: Equatable, Sendable {
    package let volume: VolumeLevel
    package let mute: MuteState

    package init(volume: VolumeLevel, mute: MuteState) {
        self.volume = volume
        self.mute = mute
    }

    package init(_ confirmed: ConfirmedMonitorState) {
        self.init(volume: confirmed.volume, mute: confirmed.mute)
    }

    package func applying(_ command: MediaKeyCommand) -> Self {
        switch command {
        case let .step(step):
            Self(volume: volume.adjusting(by: step.points), mute: .unmuted)
        case .toggleMute:
            Self(volume: volume, mute: mute.toggled)
        }
    }
}

package struct DesiredMonitorState: Sendable {
    package let session: ControlSession
    package let revision: UInt64
    package let intent: VolumeIntent
    package let measurementID: ControlMeasurementID?

    package init(session: ControlSession, revision: UInt64, intent: VolumeIntent, measurementID: ControlMeasurementID?) {
        self.session = session
        self.revision = revision
        self.intent = intent
        self.measurementID = measurementID
    }
}

package struct VolumeIntentReducer {
    private var session: ControlSession?
    private var revision: UInt64 = 0
    package private(set) var intent: VolumeIntent?

    package init() {}

    package func startingIntent(for session: ControlSession) -> VolumeIntent {
        self.session == session ? intent ?? VolumeIntent(session.seed) : VolumeIntent(session.seed)
    }

    package mutating func accept(
        _ command: MediaKeyCommand,
        session: ControlSession,
        measurementID: ControlMeasurementID? = nil
    ) -> DesiredMonitorState {
        let starting = startingIntent(for: session)
        self.session = session
        let next = starting.applying(command)
        intent = next
        revision += 1
        return DesiredMonitorState(session: session, revision: revision, intent: next, measurementID: measurementID)
    }
}
