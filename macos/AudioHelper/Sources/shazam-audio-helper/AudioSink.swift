import Foundation
import HelperCore

/// Receives mono Float32 audio at the device rate, converts it to 16 kHz s16le and writes it to stdout.
///
/// Conversion and the (possibly blocking) pipe write run on a private serial queue so that the
/// capture callbacks never wait on the reader.
final class AudioSink {
    private let queue = DispatchQueue(label: "shazam.audio-helper.output")
    private var converter: MonoPCMConverter?
    private var rate = 0.0
    private let onBrokenPipe: () -> Void

    init(onBrokenPipe: @escaping () -> Void) {
        self.onBrokenPipe = onBrokenPipe
    }

    func push(mono: [Float], sampleRate: Double) {
        guard !mono.isEmpty, sampleRate > 0 else { return }
        queue.async { [self] in
            if converter == nil || rate != sampleRate {
                converter = MonoPCMConverter(inputRate: sampleRate)
                rate = sampleRate
            }
            guard let data = converter?.convert(mono), !data.isEmpty else { return }
            if !AudioSink.writeAll(data) { onBrokenPipe() }
        }
    }

    private static func writeAll(_ data: Data) -> Bool {
        data.withUnsafeBytes { buffer in
            guard let base = buffer.baseAddress else { return true }
            var offset = 0
            while offset < buffer.count {
                let written = write(STDOUT_FILENO, base + offset, buffer.count - offset)
                if written < 0 {
                    if errno == EINTR { continue }
                    return false
                }
                offset += written
            }
            return true
        }
    }
}
