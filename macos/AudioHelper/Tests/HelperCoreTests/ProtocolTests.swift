import XCTest

@testable import HelperCore

final class ProtocolTests: XCTestCase {
    private func version(_ major: Int, _ minor: Int, _ patch: Int = 0) -> OperatingSystemVersion {
        OperatingSystemVersion(majorVersion: major, minorVersion: minor, patchVersion: patch)
    }

    func testBackendSelectionByRelease() {
        XCTAssertEqual(selectBackend(for: version(12, 7)), .none)
        XCTAssertEqual(selectBackend(for: version(13, 0)), .screenCaptureKit)
        XCTAssertEqual(selectBackend(for: version(14, 1, 9)), .screenCaptureKit)
        XCTAssertEqual(selectBackend(for: version(14, 2)), .processTap)
        XCTAssertEqual(selectBackend(for: version(15, 0)), .processTap)
        XCTAssertEqual(selectBackend(for: version(26, 0)), .processTap)
    }

    func testErrorCodesAndExitStatuses() {
        XCTAssertEqual(HelperError.permissionDenied("x").code, "permission_denied")
        XCTAssertEqual(HelperError.unsupportedOS("x").code, "unsupported_os")
        XCTAssertEqual(HelperError.captureFailed("x").code, "capture_failed")
        XCTAssertEqual(HelperError.permissionDenied("x").exitCode, 2)
        XCTAssertEqual(HelperError.unsupportedOS("x").exitCode, 3)
        XCTAssertEqual(HelperError.captureFailed("x").exitCode, 4)
    }

    func testReporterEmitsOneSortedJSONLinePerEvent() {
        var lines: [String] = []
        let reporter = Reporter { lines.append($0) }
        reporter.event("ready", ["rate": 16_000, "backend": "tap"])
        reporter.error(.permissionDenied("no"))
        XCTAssertEqual(lines[0], #"{"backend":"tap","event":"ready","rate":16000}"#)
        XCTAssertEqual(lines[1], #"{"code":"permission_denied","event":"error","message":"no"}"#)
    }
}
