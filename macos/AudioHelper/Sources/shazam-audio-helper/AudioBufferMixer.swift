import AudioToolbox
import Foundation
import HelperCore

/// Reduces a Core Audio buffer list to mono Float32.
enum AudioBufferMixer {
    /// - Parameters:
    ///   - list: buffers as delivered by an IO proc or a sample buffer.
    ///   - description: the stream format; must be linear PCM Float32.
    ///   - trailing: when the list also carries streams of other devices (an aggregate device),
    ///     take only the last stream(s), which belong to the tap.
    static func mono(
        from list: UnsafePointer<AudioBufferList>,
        description: AudioStreamBasicDescription,
        trailing: Bool = false
    ) -> [Float] {
        let buffers = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: list))
        let planar = description.mFormatFlags & kAudioFormatFlagIsNonInterleaved != 0
        let channels = max(1, Int(description.mChannelsPerFrame))

        if planar {
            let selected = trailing ? Array(buffers.suffix(channels)) : Array(buffers)
            let slices: [UnsafeBufferPointer<Float>] = selected.compactMap { buffer in
                guard let data = buffer.mData else { return nil }
                let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.size
                return UnsafeBufferPointer(start: data.assumingMemoryBound(to: Float.self), count: count)
            }
            return Mixdown.planar(slices)
        }

        guard let buffer = buffers.last, let data = buffer.mData else { return [] }
        let count = Int(buffer.mDataByteSize) / MemoryLayout<Float>.size
        let samples = UnsafeBufferPointer(start: data.assumingMemoryBound(to: Float.self), count: count)
        return Mixdown.interleaved(samples, channels: max(1, Int(buffer.mNumberChannels)))
    }

    static func isFloat32(_ description: AudioStreamBasicDescription) -> Bool {
        description.mFormatID == kAudioFormatLinearPCM
            && description.mFormatFlags & kAudioFormatFlagIsFloat != 0
            && description.mBitsPerChannel == 32
    }
}
