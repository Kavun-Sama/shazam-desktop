#!/usr/bin/env bash
# Build the macOS system-audio helper for the host architecture and copy it to OUT_DIR.
#
# usage: build_audio_helper.sh OUT_DIR
set -euo pipefail

out="${1:?usage: build_audio_helper.sh OUT_DIR}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package="$root/macos/AudioHelper"

swift build -c release --package-path "$package"
bin="$(swift build -c release --package-path "$package" --show-bin-path)/shazam-audio-helper"

mkdir -p "$out"
cp "$bin" "$out/shazam-audio-helper"
codesign --force --sign - "$out/shazam-audio-helper"

# The embedded Info.plist is what makes macOS honour the usage description for this binary.
strings -a "$out/shazam-audio-helper" | grep -q NSAudioCaptureUsageDescription \
  || { echo "helper has no embedded NSAudioCaptureUsageDescription" >&2; exit 1; }
lipo -archs "$out/shazam-audio-helper"
"$out/shazam-audio-helper" --probe
