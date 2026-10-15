"""macOS backend: microphones through PortAudio, system audio through the Swift helper."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

from shazam_desktop.audio.backend import AudioBackend, AudioStream, FrameCallback
from shazam_desktop.audio.backends import macos_system
from shazam_desktop.audio.backends.macos_system import (
    SYSTEM_HINT_NO_HELPER,
    SYSTEM_HINT_OLD_OS,
    Version,
)
from shazam_desktop.audio.sources import AudioSource, SourceCatalog, SourceKind
from shazam_desktop.errors import ErrorKind, RecognitionError


class MacOSBackend:
    """:class:`~shazam_desktop.audio.backend.AudioBackend` for macOS."""

    def __init__(
        self,
        microphones: AudioBackend,
        *,
        locate_helper: Callable[[], Path | None] = macos_system.find_helper,
        version: Callable[[], Version] = macos_system.macos_version,
    ) -> None:
        self._microphones = microphones
        self._locate_helper = locate_helper
        self._version = version

    def list_sources(self) -> SourceCatalog:
        catalog = self._microphones.list_sources()
        available, hint = self._system_availability()
        sources = tuple(
            dataclasses.replace(source, available=available, hint=hint, device=None)
            if source.kind is SourceKind.SYSTEM
            else source
            for source in catalog.sources
        )
        return SourceCatalog(sources)

    def open_stream(self, source: AudioSource, on_frames: FrameCallback) -> AudioStream:
        if source.kind is not SourceKind.SYSTEM:
            return self._microphones.open_stream(source, on_frames)
        available, hint = self._system_availability()
        helper = self._locate_helper()
        if not available or helper is None:
            raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, hint or "system audio")
        return macos_system.open_helper_stream(helper, on_frames)

    def _system_availability(self) -> tuple[bool, str | None]:
        if not macos_system.os_supports_system_audio(self._version()):
            return False, SYSTEM_HINT_OLD_OS
        if self._locate_helper() is None:
            return False, SYSTEM_HINT_NO_HELPER
        return True, None
