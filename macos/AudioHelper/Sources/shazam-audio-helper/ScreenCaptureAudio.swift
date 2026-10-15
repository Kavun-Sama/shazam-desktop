import CoreMedia
import Foundation
import HelperCore
import ScreenCaptureKit

/// System-wide capture through an audio-only ScreenCaptureKit stream (macOS 13.0 to 14.1).
///
/// The stream is attached to the main display with a minimal, slow video configuration; only the
/// audio samples are used. Screen Recording permission is required by the framework.
@available(macOS 13.0, *)
final class ScreenCaptureAudio: NSObject, AudioCapturing, SCStreamOutput, SCStreamDelegate {
    var onFailure: ((HelperError) -> Void)?

    private let queue = DispatchQueue(label: "shazam.audio-helper.sck", qos: .userInitiated)
    private var stream: SCStream?
    private var sink: AudioSink?

    func start(sink: AudioSink) async throws {
        self.sink = sink

        let content: SCShareableContent
        do {
            content = try await SCShareableContent.excludingDesktopWindows(
                false, onScreenWindowsOnly: false
            )
        } catch {
            throw ScreenCaptureAudio.classify(error)
        }
        guard let display = content.displays.first else {
            throw HelperError.captureFailed("no display is available for audio capture")
        }

        let configuration = SCStreamConfiguration()
        configuration.capturesAudio = true
        configuration.sampleRate = 16_000
        configuration.channelCount = 1
        configuration.excludesCurrentProcessAudio = true
        configuration.width = 2
        configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        do {
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue)
            // The framework logs a warning for every video frame without a screen output.
            try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
            try await stream.startCapture()
        } catch {
            throw ScreenCaptureAudio.classify(error)
        }
        self.stream = stream
    }

    func stop() {
        guard let stream else { return }
        self.stream = nil
        let semaphore = DispatchSemaphore(value: 0)
        stream.stopCapture { _ in semaphore.signal() }
        _ = semaphore.wait(timeout: .now() + 2)
    }

    // MARK: SCStreamOutput

    func stream(
        _ stream: SCStream,
        didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of type: SCStreamOutputType
    ) {
        guard type == .audio, CMSampleBufferIsValid(sampleBuffer),
            CMSampleBufferGetNumSamples(sampleBuffer) > 0
        else { return }
        guard
            let format = CMSampleBufferGetFormatDescription(sampleBuffer),
            let description = CMAudioFormatDescriptionGetStreamBasicDescription(format)?.pointee,
            AudioBufferMixer.isFloat32(description)
        else { return }

        var sizeNeeded = 0
        var status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: &sizeNeeded,
            bufferListOut: nil,
            bufferListSize: 0,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: 0,
            blockBufferOut: nil
        )
        guard status == noErr, sizeNeeded > 0 else { return }

        let storage = UnsafeMutableRawPointer.allocate(
            byteCount: sizeNeeded, alignment: MemoryLayout<AudioBufferList>.alignment
        )
        defer { storage.deallocate() }
        let list = storage.bindMemory(to: AudioBufferList.self, capacity: 1)
        var blockBuffer: CMBlockBuffer?
        status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: list,
            bufferListSize: sizeNeeded,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &blockBuffer
        )
        guard status == noErr else { return }

        let mono = AudioBufferMixer.mono(from: list, description: description)
        sink?.push(mono: mono, sampleRate: description.mSampleRate)
        withExtendedLifetime(blockBuffer) {}
    }

    // MARK: SCStreamDelegate

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        onFailure?(ScreenCaptureAudio.classify(error))
    }

    private static func classify(_ error: Error) -> HelperError {
        let code = (error as NSError).code
        if code == SCStreamError.Code.userDeclined.rawValue {
            return .permissionDenied("Screen Recording is not allowed for this app")
        }
        return .captureFailed(error.localizedDescription)
    }
}
