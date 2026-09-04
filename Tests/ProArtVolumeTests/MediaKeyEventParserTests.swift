import Testing
@testable import ProArtVolume
@testable import ProArtVolumeCore

struct MediaKeyEventParserTests {
    @Test(arguments: [
        (0, MediaKey.volumeUp),
        (1, MediaKey.volumeDown),
        (7, MediaKey.mute),
    ])
    func decodesSupportedKeyDowns(keyCode: Int, expectedKey: MediaKey) {
        let data1 = (keyCode << 16) | (0xA << 8)

        #expect(
            MediaKeyEventParser.parse(systemDefinedSubtype: 8, data1: data1)
                == MediaKeyEvent(key: expectedKey, phase: .down)
        )
    }

    @Test
    func decodesKeyUpAndIgnoresRepeatFlag() {
        let data1 = (1 << 16) | (0xB << 8) | 1

        #expect(
            MediaKeyEventParser.parse(systemDefinedSubtype: 8, data1: data1)
                == MediaKeyEvent(key: .volumeDown, phase: .up)
        )
    }

    @Test(arguments: [
        (9, (0 << 16) | (0xA << 8)),
        (8, (2 << 16) | (0xA << 8)),
        (8, (0 << 16) | (0xC << 8)),
    ])
    func rejectsUnsupportedEvents(subtype: Int, data1: Int) {
        #expect(MediaKeyEventParser.parse(systemDefinedSubtype: subtype, data1: data1) == nil)
    }
}
