import Foundation

/// Streaming sample-rate converter for one channel of Float32 audio.
///
/// Uses a Blackman-windowed sinc low-pass, so downsampling (48 kHz to 16 kHz in the common case)
/// does not alias. The converter keeps just enough history to be fed in arbitrary chunk sizes.
public final class StreamResampler {
    private static let zeroCrossings = 12.0
    private static let passbandFraction = 0.94

    private let ratio: Double
    private let cutoff: Double
    private let halfWidth: Int
    private var history: [Float] = []
    private var start = 0
    private var produced = 0

    public init(inputRate: Double, outputRate: Double) {
        precondition(inputRate > 0 && outputRate > 0, "sample rates must be positive")
        ratio = outputRate / inputRate
        cutoff = 0.5 * min(1.0, ratio) * StreamResampler.passbandFraction
        halfWidth = Int((StreamResampler.zeroCrossings / (2 * cutoff)).rounded(.up))
    }

    /// Converts the next chunk; returns the output samples that are complete so far.
    public func process(_ input: [Float]) -> [Float] {
        if ratio == 1 { return input }
        history.append(contentsOf: input)
        let end = start + history.count
        var output: [Float] = []
        output.reserveCapacity(Int(Double(input.count) * ratio) + 2)

        while true {
            let position = Double(produced) / ratio
            let center = Int(position.rounded(.down))
            if center + halfWidth >= end { break }
            var accumulator = 0.0
            for index in (center - halfWidth + 1)...(center + halfWidth) {
                let local = index - start
                if local < 0 { continue }  // before the first sample: silence
                accumulator += Double(history[local]) * kernel(Double(index) - position)
            }
            output.append(Float(accumulator))
            produced += 1
        }

        let nextCenter = Int((Double(produced) / ratio).rounded(.down))
        let keepFrom = max(start, nextCenter - halfWidth)
        if keepFrom > start {
            history.removeFirst(keepFrom - start)
            start = keepFrom
        }
        return output
    }

    private func kernel(_ t: Double) -> Double {
        let x = 2 * cutoff * t
        let sinc = x == 0 ? 1.0 : sin(Double.pi * x) / (Double.pi * x)
        let phase = t / Double(halfWidth)  // -1...1 across the support
        let window = 0.42 + 0.5 * cos(Double.pi * phase) + 0.08 * cos(2 * Double.pi * phase)
        return 2 * cutoff * sinc * window
    }
}
