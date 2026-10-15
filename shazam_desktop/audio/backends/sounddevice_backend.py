"""PortAudio input through ``sounddevice``.

Microphones work everywhere. System audio is offered only when the OS exposes a loopback
*input* device (for example a PulseAudio monitor); macOS system audio comes from the Swift
helper instead, see :mod:`shazam_desktop.audio.backends.macos_backend`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from shazam_desktop.audio.backend import AudioStream, FrameCallback, classify_open_error
from shazam_desktop.audio.pcm import Int16Array, downmix_to_mono
from shazam_desktop.audio.sources import (
    AudioSource,
    InputDevice,
    SourceCatalog,
    build_catalog,
    unavailable_catalog,
)
from shazam_desktop.errors import ErrorKind, RecognitionError

log = logging.getLogger(__name__)

LOOPBACK_MARKERS = ("soundflower", "loopback", "monitor of")
_BLOCKS_PER_SECOND = 20

SYSTEM_HINT = "System audio capture isn't supported on this platform."


def is_loopback_name(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in LOOPBACK_MARKERS)


def split_devices(
    devices: Sequence[InputDevice],
) -> tuple[list[InputDevice], InputDevice | None]:
    """Separate real microphones from the first loopback-style input device."""
    microphones: list[InputDevice] = []
    loopback: InputDevice | None = None
    for device in devices:
        if is_loopback_name(device.name):
            loopback = loopback or device
        else:
            microphones.append(device)
    return microphones, loopback


def _load() -> Any:
    import sounddevice

    return sounddevice


def _default_input_index(sd: Any) -> int | None:
    try:
        return int(sd.query_devices(kind="input")["index"])
    except (ValueError, KeyError, sd.PortAudioError):
        return None


class _SoundDeviceStream:
    def __init__(self, stream: Any, sample_rate: int) -> None:
        self._stream = stream
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def failure(self) -> RecognitionError | None:
        return None

    def close(self) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            log.warning("Failed to close the input stream cleanly", exc_info=True)


class SoundDeviceBackend:
    """:class:`~shazam_desktop.audio.backend.AudioBackend` for macOS and Linux."""

    def list_sources(self) -> SourceCatalog:
        try:
            sd = _load()
        except (ImportError, OSError) as exc:
            return unavailable_catalog(f"Audio backend unavailable: {exc}")
        try:
            raw_devices = list(sd.query_devices())
            default_index = _default_input_index(sd)
        except sd.PortAudioError as exc:
            return unavailable_catalog(f"Audio backend unavailable: {exc}")

        inputs = [
            InputDevice(index=index, name=str(info["name"]))
            for index, info in enumerate(raw_devices)
            if info["max_input_channels"] > 0
        ]
        microphones, loopback = split_devices(inputs)
        return build_catalog(microphones, default_index, loopback, SYSTEM_HINT)

    def open_stream(self, source: AudioSource, on_frames: FrameCallback) -> AudioStream:
        if source.device is None:
            raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, source.label)
        try:
            sd = _load()
        except (ImportError, OSError) as exc:
            raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, str(exc)) from exc

        def callback(indata: Int16Array, frames: int, time_info: object, status: object) -> None:
            on_frames(downmix_to_mono(indata))

        try:
            info = sd.query_devices(source.device)
            channels = max(1, min(int(info["max_input_channels"]), 2))
            sample_rate = int(info["default_samplerate"])
            stream = sd.InputStream(
                device=source.device,
                channels=channels,
                samplerate=sample_rate,
                dtype="int16",
                blocksize=sample_rate // _BLOCKS_PER_SECOND,
                callback=callback,
            )
            stream.start()
        except sd.PortAudioError as exc:
            raise RecognitionError(classify_open_error(str(exc)), str(exc)) from exc
        return _SoundDeviceStream(stream, sample_rate)
