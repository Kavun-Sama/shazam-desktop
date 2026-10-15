"""User-facing copy for every error card."""

from __future__ import annotations

from shazam_desktop.errors import ErrorKind
from shazam_desktop.state import Phase

IDLE_HINT = "Tap to identify"

ERROR_COPY: dict[ErrorKind, tuple[str, str]] = {
    ErrorKind.NO_MATCH: ("No match", "Couldn't identify this one. Try again closer to the source."),
    ErrorKind.NETWORK: ("Can't reach Shazam", "Check your internet connection."),
    ErrorKind.FFMPEG_MISSING: ("ffmpeg not found", "Add ffmpeg and ffprobe to PATH."),
    ErrorKind.SOURCE_UNAVAILABLE: (
        "No audio from source",
        "Check it's connected and playing, or pick another.",
    ),
    ErrorKind.PERMISSION_DENIED: (
        "Microphone access blocked",
        "Allow access in system privacy settings.",
    ),
    ErrorKind.SYSTEM_AUDIO_DENIED: (
        "System audio blocked",
        "Allow it in Privacy & Security, then try again.",
    ),
    ErrorKind.HELPER_FAILED: (
        "Audio helper stopped",
        "Try again. If it keeps happening, reinstall the app.",
    ),
    ErrorKind.UNEXPECTED: ("Something went wrong", "Try again."),
}

PHASE_TEXT: dict[Phase, str] = {
    Phase.LISTENING: "Listening…",
    Phase.FINGERPRINTING: "Fingerprinting…",
    Phase.MATCHING: "Matching…",
}
