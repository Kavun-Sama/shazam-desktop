import Foundation

/// Writes one JSON object per line to a sink (stderr by default).
///
/// stdout is reserved for PCM, so every diagnostic goes through this type.
public struct Reporter {
    private let write: (String) -> Void

    public init(write: @escaping (String) -> Void = Reporter.writeToStandardError) {
        self.write = write
    }

    public static func writeToStandardError(_ line: String) {
        FileHandle.standardError.write(Data((line + "\n").utf8))
    }

    public func event(_ name: String, _ fields: [String: Any] = [:]) {
        var payload = fields
        payload["event"] = name
        write(Reporter.encode(payload))
    }

    public func error(_ failure: HelperError) {
        event("error", ["code": failure.code, "message": failure.message])
    }

    public static func encode(_ payload: [String: Any]) -> String {
        guard
            JSONSerialization.isValidJSONObject(payload),
            let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
            let text = String(data: data, encoding: .utf8)
        else {
            return "{\"event\":\"error\",\"code\":\"capture_failed\",\"message\":\"unencodable event\"}"
        }
        return text
    }
}
