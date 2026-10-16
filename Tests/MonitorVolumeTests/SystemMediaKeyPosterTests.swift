import Testing
@testable import MonitorVolume
@testable import MonitorVolumeCore

struct SystemMediaKeyPosterTests {
    @Test(arguments: [
        (MediaKey.volumeUp, MediaKeyPhase.down, 0x000A00),
        (.volumeUp, .up, 0x000B00),
        (.volumeDown, .down, 0x010A00),
        (.volumeDown, .up, 0x010B00),
        (.mute, .down, 0x070A00),
        (.mute, .up, 0x070B00),
    ])
    func eventDataMatchesAPhysicalKeyAndParsesBack(key: MediaKey, phase: MediaKeyPhase, data1: Int) {
        let event = MediaKeyEvent(key: key, phase: phase)

        let data = SystemMediaKeyPoster.eventData(for: event)

        #expect(data.subtype == 8)
        #expect(data.data1 == data1)
        #expect(MediaKeyEventParser.parse(systemDefinedSubtype: data.subtype, data1: data.data1) == event)
    }
}
