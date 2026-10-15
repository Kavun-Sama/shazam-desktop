import Foundation
import HelperCore

// Captures the system audio mix and writes it to stdout as raw PCM: 16 kHz, mono, s16le.
//
//   shazam-audio-helper [capture] [--backend tap|sck]   stream PCM until stdin closes or SIGTERM
//   shazam-audio-helper --probe                          print capabilities as JSON and exit
//
// Diagnostics are JSON lines on stderr (events: permission_prompt, ready, error). Exit status:
// 0 clean stop, 2 permission denied, 3 unsupported macOS, 4 any other capture failure.

signal(SIGPIPE, SIG_IGN)

let reporter = Reporter()
let version = ProcessInfo.processInfo.operatingSystemVersion
var forcedBackend: CaptureBackend?
var probe = false

var arguments = Array(CommandLine.arguments.dropFirst())
while let argument = arguments.first {
    arguments.removeFirst()
    switch argument {
    case "capture":
        break
    case "--probe":
        probe = true
    case "--backend":
        guard let name = arguments.first, let backend = CaptureBackend(rawValue: name) else {
            FileHandle.standardError.write(Data("usage: --backend tap|sck\n".utf8))
            exit(64)
        }
        arguments.removeFirst()
        forcedBackend = backend
    default:
        FileHandle.standardError.write(Data("unknown argument: \(argument)\n".utf8))
        exit(64)
    }
}

let backend = forcedBackend ?? selectBackend(for: version)

if probe {
    var info: [String: Any] = [
        "backend": backend.rawValue,
        "os": describe(version),
        "format": "s16le",
        "rate": Int(MonoPCMConverter.outputRate),
        "channels": 1,
    ]
    if backend == .processTap {
        info["permission"] = "\(TCC.audioCaptureStatus())"
    }
    print(Reporter.encode(info))
    exit(0)
}

func fail(_ failure: HelperError) -> Never {
    reporter.error(failure)
    exit(failure.exitCode)
}

func makeCapture() -> AudioCapturing {
    switch backend {
    case .processTap:
        if #available(macOS 14.2, *) { return TapCapture(reporter: reporter) }
        fail(.unsupportedOS("process taps need macOS 14.2 or newer"))
    case .screenCaptureKit:
        if #available(macOS 13.0, *) { return ScreenCaptureAudio() }
        fail(.unsupportedOS("ScreenCaptureKit audio needs macOS 13 or newer"))
    case .none:
        fail(.unsupportedOS("system audio capture needs macOS 13 or newer (found \(describe(version)))"))
    }
}

let capture = makeCapture()
let sink = AudioSink(onBrokenPipe: { exit(0) })
capture.onFailure = { fail($0) }

func shutDown() -> Never {
    capture.stop()
    exit(0)
}

var signalSources: [DispatchSourceSignal] = []
for number in [SIGTERM, SIGINT] {
    signal(number, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
    source.setEventHandler { shutDown() }
    source.resume()
    signalSources.append(source)
}

// The host keeps our stdin open; its closing is the request to stop (and covers a crashed host).
DispatchQueue.global().async {
    var byte: UInt8 = 0
    while true {
        let count = read(STDIN_FILENO, &byte, 1)
        if count == 0 || (count < 0 && errno != EINTR) { break }
    }
    DispatchQueue.main.async { shutDown() }
}

Task {
    do {
        try await capture.start(sink: sink)
        reporter.event("ready", ["backend": backend.rawValue, "rate": Int(MonoPCMConverter.outputRate)])
    } catch let failure as HelperError {
        fail(failure)
    } catch {
        fail(.captureFailed(error.localizedDescription))
    }
}

dispatchMain()
