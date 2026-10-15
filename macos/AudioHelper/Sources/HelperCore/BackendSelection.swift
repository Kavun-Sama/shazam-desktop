import Foundation

/// The capture mechanism used for a given macOS release.
public enum CaptureBackend: String {
    /// Core Audio process tap, macOS 14.2 and newer.
    case processTap = "tap"
    /// ScreenCaptureKit audio stream, macOS 13.0 up to 14.1.
    case screenCaptureKit = "sck"
    /// No supported mechanism (macOS before 13).
    case none
}

public func selectBackend(for version: OperatingSystemVersion) -> CaptureBackend {
    if version.majorVersion > 14 || (version.majorVersion == 14 && version.minorVersion >= 2) {
        return .processTap
    }
    if version.majorVersion >= 13 {
        return .screenCaptureKit
    }
    return .none
}

public func describe(_ version: OperatingSystemVersion) -> String {
    "\(version.majorVersion).\(version.minorVersion).\(version.patchVersion)"
}
