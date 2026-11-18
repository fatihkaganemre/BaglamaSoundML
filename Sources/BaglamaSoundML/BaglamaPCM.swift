import Foundation

public struct BaglamaPCM: Sendable {
    public static let sampleRate = 48_000
    public let samples: [Float]

    /// Encode a mono 16-bit PCM WAV. Call outside real-time audio callbacks.
    public func wavData() -> Data {
        var data = Data()
        func text(_ value: String) { data.append(contentsOf: value.utf8) }
        func integer<T: FixedWidthInteger>(_ value: T) {
            var littleEndian = value.littleEndian
            withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
        }
        text("RIFF")
        integer(UInt32(36 + samples.count * 2))
        text("WAVEfmt ")
        integer(UInt32(16))
        integer(UInt16(1))
        integer(UInt16(1))
        integer(UInt32(Self.sampleRate))
        integer(UInt32(Self.sampleRate * 2))
        integer(UInt16(2))
        integer(UInt16(16))
        text("data")
        integer(UInt32(samples.count * 2))
        for sample in samples { integer(Int16((max(-1, min(1, sample)) * 32_767).rounded())) }
        return data
    }
}
