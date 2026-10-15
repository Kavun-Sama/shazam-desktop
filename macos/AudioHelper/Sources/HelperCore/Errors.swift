import Foundation

/// Failures the helper reports to the host process.
///
/// Each case maps to a stable machine-readable ``code`` (sent in the JSON error event) and to the
/// process exit status, so the host can classify a failure even if stderr is lost.
public enum HelperError: Error, Equatable {
    /// The user has not granted (or has revoked) the system-audio / screen-recording permission.
    case permissionDenied(String)
    /// The OS is too old for any capture backend.
    case unsupportedOS(String)
    /// Any other capture failure.
    case captureFailed(String)

    public var code: String {
        switch self {
        case .permissionDenied: return "permission_denied"
        case .unsupportedOS: return "unsupported_os"
        case .captureFailed: return "capture_failed"
        }
    }

    public var message: String {
        switch self {
        case .permissionDenied(let text), .unsupportedOS(let text), .captureFailed(let text):
            return text
        }
    }

    public var exitCode: Int32 {
        switch self {
        case .permissionDenied: return 2
        case .unsupportedOS: return 3
        case .captureFailed: return 4
        }
    }
}
