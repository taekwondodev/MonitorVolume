import Foundation

public enum RemoteFrameError: Error, Equatable, Sendable {
    case frameTooLarge
    case malformed
    case unsupportedVersion(Int)
    case unknownKey(String)
    case unknownPhase(String)
}

/// One command is one JSON object on one newline-terminated line.
public enum RemoteCommandCodec {
    public static let version = 1
    /// Upper bound for one frame, including its terminating newline.
    public static let maximumFrameBytes = 256
    static let terminator = UInt8(ascii: "\n")

    public static func encode(_ command: RemoteCommand) -> Data {
        let frame = WireCommand(version: version, key: command.key.rawValue, phase: command.phase.rawValue)
        // Three short strings and an integer always encode.
        var data = (try? encoder.encode(frame)) ?? Data()
        data.append(terminator)
        return data
    }

    /// Decodes one line whose terminating newline has been removed.
    public static func decode(line: Data) throws(RemoteFrameError) -> RemoteCommand {
        guard line.count < maximumFrameBytes else { throw .frameTooLarge }
        guard let frame = try? JSONDecoder().decode(WireCommand.self, from: line) else {
            throw .malformed
        }
        guard frame.version == version else { throw .unsupportedVersion(frame.version) }
        guard let key = RemoteKey(rawValue: frame.key) else { throw .unknownKey(frame.key) }
        guard let phase = RemotePhase(rawValue: frame.phase) else { throw .unknownPhase(frame.phase) }
        return RemoteCommand(key: key, phase: phase)
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return encoder
    }()
}

private struct WireCommand: Codable {
    let version: Int
    let key: String
    let phase: String
}
