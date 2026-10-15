import AudioToolbox
import CoreAudio
import Foundation
import HelperCore

/// System-wide capture through a Core Audio process tap (macOS 14.2+).
///
/// A global tap mixes the output of every process into a stereo stream. The tap is wrapped in a
/// private aggregate device so that an IO proc can read it like an input device.
@available(macOS 14.2, *)
final class TapCapture: AudioCapturing {
    var onFailure: ((HelperError) -> Void)?

    private let reporter: Reporter
    private let queue = DispatchQueue(label: "shazam.audio-helper.tap", qos: .userInitiated)
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var procID: AudioDeviceIOProcID?
    private var watchdog: DispatchSourceTimer?
    private let activity = Activity()

    init(reporter: Reporter) {
        self.reporter = reporter
    }

    func start(sink: AudioSink) async throws {
        try ensurePermission()

        let description = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
        description.name = "Shazam Desktop system audio"
        description.isPrivate = true
        description.muteBehavior = .unmuted

        var tap = AudioObjectID(kAudioObjectUnknown)
        var status = AudioHardwareCreateProcessTap(description, &tap)
        guard status == noErr else {
            throw HelperError.captureFailed("AudioHardwareCreateProcessTap failed (\(status))")
        }
        tapID = tap

        let format = try tapFormat(tap)
        guard AudioBufferMixer.isFloat32(format) else {
            throw HelperError.captureFailed("unsupported tap format (flags \(format.mFormatFlags))")
        }

        let outputUID = try defaultOutputDeviceUID()
        let aggregate: [String: Any] = [
            kAudioAggregateDeviceNameKey: "Shazam Desktop tap",
            kAudioAggregateDeviceUIDKey: UUID().uuidString,
            kAudioAggregateDeviceMainSubDeviceKey: outputUID,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
            kAudioAggregateDeviceTapListKey: [
                [
                    kAudioSubTapDriftCompensationKey: true,
                    kAudioSubTapUIDKey: description.uuid.uuidString,
                ],
            ],
        ]
        var device = AudioObjectID(kAudioObjectUnknown)
        status = AudioHardwareCreateAggregateDevice(aggregate as CFDictionary, &device)
        guard status == noErr else {
            throw HelperError.captureFailed("AudioHardwareCreateAggregateDevice failed (\(status))")
        }
        aggregateID = device

        let rate = format.mSampleRate
        let activity = self.activity
        status = AudioDeviceCreateIOProcIDWithBlock(&procID, device, queue) {
            _, input, _, _, _ in
            let mono = AudioBufferMixer.mono(from: input, description: format, trailing: true)
            if mono.isEmpty { return }
            if mono.contains(where: { $0 != 0 }) { activity.markSound() }
            sink.push(mono: mono, sampleRate: rate)
        }
        guard status == noErr, procID != nil else {
            throw HelperError.captureFailed("AudioDeviceCreateIOProcIDWithBlock failed (\(status))")
        }

        status = AudioDeviceStart(device, procID)
        guard status == noErr else {
            throw HelperError.captureFailed("AudioDeviceStart failed (\(status))")
        }
        startWatchdog()
    }

    func stop() {
        watchdog?.cancel()
        watchdog = nil
        if aggregateID != kAudioObjectUnknown {
            AudioDeviceStop(aggregateID, procID)
            if let procID { AudioDeviceDestroyIOProcID(aggregateID, procID) }
            AudioHardwareDestroyAggregateDevice(aggregateID)
        }
        if tapID != kAudioObjectUnknown {
            AudioHardwareDestroyProcessTap(tapID)
        }
        procID = nil
        aggregateID = AudioObjectID(kAudioObjectUnknown)
        tapID = AudioObjectID(kAudioObjectUnknown)
    }

    // MARK: Permission

    private func ensurePermission() throws {
        switch TCC.audioCaptureStatus() {
        case .granted, .unknown:
            return
        case .denied:
            throw HelperError.permissionDenied("System audio recording is not allowed for this app")
        case .undetermined:
            reporter.event("permission_prompt")
            if let allowed = TCC.requestAudioCapture(timeout: 120), !allowed {
                throw HelperError.permissionDenied("System audio recording was not allowed")
            }
        }
    }

    /// A refusal that arrives after start shows up as endless digital silence: catch it by
    /// asking TCC again while nothing but zeros has been delivered.
    private func startWatchdog() {
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + 1.5, repeating: 0.5)
        timer.setEventHandler { [weak self] in
            guard let self, !self.activity.heardSound else { return }
            if TCC.audioCaptureStatus() == .denied {
                self.onFailure?(.permissionDenied("System audio recording was revoked"))
            }
        }
        watchdog = timer
        timer.resume()
    }

    // MARK: Core Audio queries

    private func tapFormat(_ tap: AudioObjectID) throws -> AudioStreamBasicDescription {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioTapPropertyFormat,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var format = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        let status = AudioObjectGetPropertyData(tap, &address, 0, nil, &size, &format)
        guard status == noErr else {
            throw HelperError.captureFailed("reading the tap format failed (\(status))")
        }
        return format
    }

    private func defaultOutputDeviceUID() throws -> String {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var device = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        var status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &device
        )
        guard status == noErr, device != kAudioObjectUnknown else {
            throw HelperError.captureFailed("no default output device (\(status))")
        }

        address.mSelector = kAudioDevicePropertyDeviceUID
        var uid: Unmanaged<CFString>?
        size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &uid)
        guard status == noErr, let uid else {
            throw HelperError.captureFailed("reading the output device UID failed (\(status))")
        }
        return uid.takeRetainedValue() as String
    }
}

/// Whether anything but zeros has been delivered yet; written on the IO queue, read on the timer.
private final class Activity {
    private let lock = NSLock()
    private var sound = false

    var heardSound: Bool {
        lock.lock()
        defer { lock.unlock() }
        return sound
    }

    func markSound() {
        lock.lock()
        sound = true
        lock.unlock()
    }
}
