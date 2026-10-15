#!/usr/bin/env bash
# Build minimal LGPL ffmpeg and ffprobe from the pinned upstream source tarball.
#
# Usage: packaging/build_ffmpeg.sh OUTPUT_DIR
#
# The binaries only decode and encode PCM WAV, which is all pydub (inside ShazamAPI) asks for.
# GPL and nonfree code, external libraries and autodetected features are switched off, so the
# result is LGPL-2.1+ and has no runtime dependencies beyond the OS.
set -euo pipefail

FFMPEG_VERSION="8.1.3"
FFMPEG_SHA256="7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3"
FFMPEG_URL="https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz"

output_dir="${1:?usage: build_ffmpeg.sh OUTPUT_DIR}"
jobs="${FFMPEG_JOBS:-$( (nproc || sysctl -n hw.ncpu) 2>/dev/null || echo 2)}"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

echo "Downloading FFmpeg ${FFMPEG_VERSION}"
curl -fsSL --retry 5 --retry-delay 3 -o "$work_dir/ffmpeg.tar.xz" "$FFMPEG_URL"
actual="$(sha256_of "$work_dir/ffmpeg.tar.xz")"
if [ "$actual" != "$FFMPEG_SHA256" ]; then
  echo "SHA256 mismatch for ${FFMPEG_URL}: expected ${FFMPEG_SHA256}, got ${actual}" >&2
  exit 1
fi
tar -xf "$work_dir/ffmpeg.tar.xz" -C "$work_dir"

configure_args=(
  --disable-gpl --disable-nonfree --disable-version3
  --disable-autodetect --disable-everything
  --disable-doc --disable-debug --disable-network --disable-asm
  --disable-ffplay --disable-avdevice --disable-swscale
  --enable-static --disable-shared
  --enable-protocol=file,pipe,fd,cache
  --enable-demuxer=wav
  --enable-muxer=wav
  --enable-decoder=pcm_s16le,pcm_s16be,pcm_u8,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le
  --enable-encoder=pcm_s16le
  --enable-filter=aresample,aformat,anull,abuffer,abuffersink
)

case "$(uname -s)" in
  Darwin)
    configure_args+=(--extra-cflags=-mmacosx-version-min=11.0 --extra-ldflags=-mmacosx-version-min=11.0)
    ;;
  MINGW* | MSYS*)
    configure_args+=(--target-os=mingw32 --arch=x86_64 --extra-ldflags=-static)
    ;;
esac

cd "$work_dir/ffmpeg-${FFMPEG_VERSION}"
./configure "${configure_args[@]}"
make -j"$jobs" ffmpeg ffprobe

mkdir -p "$output_dir"
for tool in ffmpeg ffprobe; do
  binary="$tool"
  [ -f "${tool}.exe" ] && binary="${tool}.exe"
  strip "$binary" 2>/dev/null || true
  cp "$binary" "$output_dir/$binary"
done

# The license must be LGPL; refuse to hand back anything else.
if "$output_dir"/ffmpeg -hide_banner -buildconf 2>&1 | grep -E -- '--enable-(gpl|nonfree|version3)'; then
  echo "Built ffmpeg is not LGPL-2.1+" >&2
  exit 1
fi
"$output_dir"/ffmpeg -hide_banner -version | head -3
