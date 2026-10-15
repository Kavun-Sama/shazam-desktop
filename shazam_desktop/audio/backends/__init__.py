"""Platform audio backends."""

from __future__ import annotations

import sys

from shazam_desktop.audio.backend import AudioBackend


def create_backend() -> AudioBackend:
    """Return the backend for the current platform."""
    if sys.platform == "win32":
        from shazam_desktop.audio.backends.wasapi_backend import WasapiBackend

        return WasapiBackend()
    from shazam_desktop.audio.backends.sounddevice_backend import SoundDeviceBackend

    return SoundDeviceBackend()
