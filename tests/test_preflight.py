from __future__ import annotations

from shazam_desktop.recognition.preflight import ffmpeg_available


def test_requires_both_binaries() -> None:
    assert ffmpeg_available(lambda name: f"/usr/bin/{name}")
    assert not ffmpeg_available(lambda name: None)
    assert not ffmpeg_available(lambda name: None if name == "ffprobe" else "/usr/bin/ffmpeg")
