import Foundation

/// Status of the "System Audio Recording" privacy permission (`kTCCServiceAudioCapture`).
enum AudioCapturePermission {
    case granted
    case denied
    case undetermined
    /// The private TCC entry points could not be resolved on this macOS release.
    case unknown
}

/// Access to the TCC framework.
///
/// Core Audio taps have no public API to query the permission: with a missing grant, tap creation
/// and the IO proc both "succeed" but deliver zeros. The same private entry points that the system
/// frameworks use (`TCCAccessPreflight`, `TCCAccessRequest`) are therefore resolved at run time;
/// when they are missing the helper falls back to a silence watchdog.
enum TCC {
    private typealias PreflightFunction = @convention(c) (CFString, CFDictionary?) -> Int32
    private typealias RequestFunction = @convention(c) (
        CFString, CFDictionary?, @escaping @convention(block) (Bool) -> Void
    ) -> Void

    private static let service = "kTCCServiceAudioCapture" as CFString
    private static let library = dlopen(
        "/System/Library/PrivateFrameworks/TCC.framework/Versions/A/TCC", RTLD_NOW
    )

    private static func symbol(_ name: String) -> UnsafeMutableRawPointer? {
        guard let library else { return nil }
        return dlsym(library, name)
    }

    static func audioCaptureStatus() -> AudioCapturePermission {
        guard let pointer = symbol("TCCAccessPreflight") else { return .unknown }
        let preflight = unsafeBitCast(pointer, to: PreflightFunction.self)
        switch preflight(service, nil) {
        case 0: return .granted
        case 1: return .denied
        default: return .undetermined
        }
    }

    /// Shows the system prompt and waits for the answer. Returns `nil` when the request entry
    /// point is unavailable, `false` when the user refused (or did not answer in time).
    static func requestAudioCapture(timeout: TimeInterval) -> Bool? {
        guard let pointer = symbol("TCCAccessRequest") else { return nil }
        let request = unsafeBitCast(pointer, to: RequestFunction.self)
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false
        request(service, nil) { allowed in
            granted = allowed
            semaphore.signal()
        }
        guard semaphore.wait(timeout: .now() + timeout) == .success else { return false }
        return granted
    }
}
