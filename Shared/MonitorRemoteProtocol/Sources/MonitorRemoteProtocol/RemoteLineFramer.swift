import Foundation

/// Splits a byte stream into newline-terminated lines, holding at most one
/// partial frame of `RemoteCommandCodec.maximumFrameBytes`.
public struct RemoteLineFramer: Sendable {
    private var pending = Data()

    public init() {}

    /// Returns every complete line in arrival order, without terminators.
    /// Throws when a line, or the partial line still pending, exceeds the frame bound.
    public mutating func append(_ bytes: Data) throws(RemoteFrameError) -> [Data] {
        pending.append(bytes)
        var lines: [Data] = []
        while let end = pending.firstIndex(of: RemoteCommandCodec.terminator) {
            let line = pending[pending.startIndex..<end]
            guard line.count < RemoteCommandCodec.maximumFrameBytes else { throw .frameTooLarge }
            lines.append(Data(line))
            pending = Data(pending[pending.index(after: end)...])
        }
        guard pending.count < RemoteCommandCodec.maximumFrameBytes else { throw .frameTooLarge }
        return lines
    }
}
