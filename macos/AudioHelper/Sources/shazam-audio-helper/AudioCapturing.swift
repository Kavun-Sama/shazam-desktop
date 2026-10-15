import Foundation
import HelperCore

/// A source of system audio. Implementations push mono Float32 chunks into an ``AudioSink``.
protocol AudioCapturing: AnyObject {
    /// Called when a running capture fails (the permission was revoked, the stream was stopped).
    var onFailure: ((HelperError) -> Void)? { get set }

    /// Resolves once audio is actually being delivered; throws a ``HelperError`` otherwise.
    func start(sink: AudioSink) async throws

    func stop()
}
