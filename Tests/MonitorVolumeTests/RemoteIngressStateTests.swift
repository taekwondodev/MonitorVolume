import Foundation
import Testing
@testable import MonitorVolume
@testable import MonitorVolumeCore

struct RemoteIngressStateTests {
    @Test
    func pressAndReleaseAreForwardedAsTheMatchingMediaKey() {
        var ingress = RemoteIngressState()
        _ = ingress.adopt(1)

        let receipt = ingress.receive(frames(
            #"{"version":1,"key":"volumeDown","phase":"down"}"#,
            #"{"version":1,"key":"volumeDown","phase":"down"}"#,
            #"{"version":1,"key":"volumeDown","phase":"up"}"#
        ), on: 1)

        #expect(receipt == RemoteReceipt(events: [keyDown(.volumeDown), keyDown(.volumeDown), keyUp(.volumeDown)]))
    }

    @Test
    func disconnectReleasesEveryHeldKey() {
        var ingress = RemoteIngressState()
        _ = ingress.adopt(1)
        _ = ingress.receive(frames(
            #"{"version":1,"key":"mute","phase":"down"}"#,
            #"{"version":1,"key":"volumeUp","phase":"down"}"#
        ), on: 1)

        #expect(ingress.close(1) == [keyUp(.volumeUp), keyUp(.mute)])
        #expect(ingress.close(1).isEmpty)
    }

    @Test
    func replacingConnectionReleasesTheOldHeldKeysFirst() {
        var ingress = RemoteIngressState()
        _ = ingress.adopt(1)
        _ = ingress.receive(frames(#"{"version":1,"key":"volumeUp","phase":"down"}"#), on: 1)

        #expect(ingress.adopt(2) == [keyUp(.volumeUp)])
        #expect(ingress.receive(frames(#"{"version":1,"key":"volumeUp","phase":"up"}"#), on: 1)
            == RemoteReceipt(closesConnection: true))
        #expect(ingress.close(1).isEmpty)
        #expect(ingress.receive(frames(#"{"version":1,"key":"mute","phase":"down"}"#), on: 2)
            == RemoteReceipt(events: [keyDown(.mute)]))
    }

    @Test
    func unpairedKeyUpYieldsNothing() {
        var ingress = RemoteIngressState()
        _ = ingress.adopt(1)

        #expect(ingress.receive(frames(#"{"version":1,"key":"mute","phase":"up"}"#), on: 1) == RemoteReceipt())
    }

    @Test(arguments: [
        Data("not json\n".utf8),
        Data((#"{"version":2,"key":"mute","phase":"down"}"# + "\n").utf8),
        Data(repeating: UInt8(ascii: " "), count: 300),
    ])
    func malformedFrameClosesTheConnectionWithoutPosting(_ bytes: Data) {
        var ingress = RemoteIngressState()
        _ = ingress.adopt(1)

        #expect(ingress.receive(bytes, on: 1) == RemoteReceipt(closesConnection: true))
        #expect(ingress.close(1).isEmpty)
    }

    @Test
    func malformedFrameReleasesKeysHeldBeforeIt() {
        var ingress = RemoteIngressState()
        _ = ingress.adopt(1)
        _ = ingress.receive(frames(#"{"version":1,"key":"volumeDown","phase":"down"}"#), on: 1)

        #expect(ingress.receive(Data("garbage\n".utf8), on: 1)
            == RemoteReceipt(events: [keyUp(.volumeDown)], closesConnection: true))
    }

    private func frames(_ lines: String...) -> Data {
        Data(lines.map { $0 + "\n" }.joined().utf8)
    }
}
