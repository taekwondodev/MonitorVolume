import Foundation
import Testing
import MonitorRemoteProtocol

struct RemoteCommandCodecTests {
    @Test(arguments: RemoteKey.allCases, RemotePhase.allCases)
    func everyKeyAndPhaseRoundTrips(key: RemoteKey, phase: RemotePhase) throws {
        let command = RemoteCommand(key: key, phase: phase)
        var framer = RemoteLineFramer()

        let lines = try framer.append(RemoteCommandCodec.encode(command))

        #expect(lines.count == 1)
        #expect(try RemoteCommandCodec.decode(line: try #require(lines.first)) == command)
    }

    @Test
    func decodesTheDocumentedWireShape() throws {
        let line = Data(#"{"version":1,"key":"mute","phase":"up"}"#.utf8)

        #expect(try RemoteCommandCodec.decode(line: line) == RemoteCommand(key: .mute, phase: .up))
    }

    @Test(arguments: [
        (#"{"version":2,"key":"mute","phase":"down"}"#, RemoteFrameError.unsupportedVersion(2)),
        (#"{"version":1,"key":"brightnessUp","phase":"down"}"#, .unknownKey("brightnessUp")),
        (#"{"version":1,"key":"mute","phase":"repeat"}"#, .unknownPhase("repeat")),
        (#"{"version":1,"key":"mute""#, .malformed),
        (#"{"version":"1","key":"mute","phase":"down"}"#, .malformed),
        ("not json", .malformed),
    ])
    func rejectsInvalidFrames(line: String, expected: RemoteFrameError) {
        #expect(throws: expected) {
            try RemoteCommandCodec.decode(line: Data(line.utf8))
        }
    }

    @Test
    func rejectsALineOver256Bytes() {
        var framer = RemoteLineFramer()
        let line = Data(repeating: UInt8(ascii: " "), count: 256) + Data("\n".utf8)

        #expect(throws: RemoteFrameError.frameTooLarge) {
            try framer.append(line)
        }
        #expect(throws: RemoteFrameError.frameTooLarge) {
            try RemoteCommandCodec.decode(line: Data(repeating: UInt8(ascii: " "), count: 256))
        }
    }

    @Test
    func rejectsAnUnterminatedLineOnceItCanNoLongerFit() throws {
        var framer = RemoteLineFramer()

        #expect(try framer.append(Data(repeating: UInt8(ascii: " "), count: 255)).isEmpty)
        #expect(throws: RemoteFrameError.frameTooLarge) {
            try framer.append(Data(" ".utf8))
        }
    }

    @Test
    func acceptsA256ByteFrameAndJoinsSplitChunks() throws {
        var framer = RemoteLineFramer()
        let padded = Data(#"{"version":1,"key":"volumeUp","phase":"down"}"#.utf8)
            + Data(repeating: UInt8(ascii: " "), count: 255 - 45)

        #expect(try framer.append(padded.prefix(100)).isEmpty)
        let lines = try framer.append(padded.dropFirst(100) + Data("\n".utf8))

        #expect(lines.count == 1)
        #expect(try RemoteCommandCodec.decode(line: try #require(lines.first))
            == RemoteCommand(key: .volumeUp, phase: .down))
    }
}
