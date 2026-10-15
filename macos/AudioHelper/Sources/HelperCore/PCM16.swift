import Foundation

/// Signed 16-bit little-endian PCM encoding.
public enum PCM16 {
    public static func encode(_ samples: [Float]) -> Data {
        var data = Data(count: samples.count * MemoryLayout<Int16>.size)
        data.withUnsafeMutableBytes { raw in
            let target = raw.bindMemory(to: Int16.self)
            for (index, sample) in samples.enumerated() {
                let scaled = (sample * 32767).rounded()
                let clamped = scaled.isFinite ? max(-32768, min(32767, scaled)) : 0
                target[index] = Int16(clamped).littleEndian
            }
        }
        return data
    }
}

/// Mono Float32 at any rate in, 16 kHz s16le out.
public final class MonoPCMConverter {
    public static let outputRate = 16_000.0

    private let resampler: StreamResampler

    public init(inputRate: Double) {
        resampler = StreamResampler(inputRate: inputRate, outputRate: MonoPCMConverter.outputRate)
    }

    public func convert(_ mono: [Float]) -> Data {
        PCM16.encode(resampler.process(mono))
    }
}
