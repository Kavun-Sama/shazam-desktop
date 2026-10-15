/// Channel mixdown of Float32 audio to a single channel by averaging.
public enum Mixdown {
    /// Interleaved frames (`L R L R …`) to mono.
    public static func interleaved(_ samples: UnsafeBufferPointer<Float>, channels: Int) -> [Float] {
        guard channels > 0, samples.count >= channels else { return [] }
        if channels == 1 { return Array(samples) }
        let frames = samples.count / channels
        var mono = [Float](repeating: 0, count: frames)
        let scale = 1 / Float(channels)
        for frame in 0..<frames {
            var sum: Float = 0
            let base = frame * channels
            for channel in 0..<channels { sum += samples[base + channel] }
            mono[frame] = sum * scale
        }
        return mono
    }

    /// One buffer per channel (planar) to mono; stops at the shortest channel.
    public static func planar(_ channels: [UnsafeBufferPointer<Float>]) -> [Float] {
        guard let first = channels.first else { return [] }
        if channels.count == 1 { return Array(first) }
        let frames = channels.map(\.count).min() ?? 0
        var mono = [Float](repeating: 0, count: frames)
        let scale = 1 / Float(channels.count)
        for frame in 0..<frames {
            var sum: Float = 0
            for channel in channels { sum += channel[frame] }
            mono[frame] = sum * scale
        }
        return mono
    }
}
