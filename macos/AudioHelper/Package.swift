// swift-tools-version:5.9
import PackageDescription

// The linker embeds Support/Info.plist into the executable, so the helper carries its own
// usage descriptions (NSAudioCaptureUsageDescription) even when TCC attributes the request
// to the helper instead of the app that launched it.
let embeddedPlist = Context.packageDirectory + "/Support/Info.plist"

let package = Package(
    name: "AudioHelper",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "shazam-audio-helper", targets: ["shazam-audio-helper"]),
    ],
    targets: [
        // Platform-independent audio math and protocol types; unit-tested on any host.
        .target(name: "HelperCore"),
        .executableTarget(
            name: "shazam-audio-helper",
            dependencies: ["HelperCore"],
            linkerSettings: [
                .unsafeFlags([
                    "-Xlinker", "-sectcreate",
                    "-Xlinker", "__TEXT",
                    "-Xlinker", "__info_plist",
                    "-Xlinker", embeddedPlist,
                ]),
            ]
        ),
        .testTarget(name: "HelperCoreTests", dependencies: ["HelperCore"]),
    ]
)
