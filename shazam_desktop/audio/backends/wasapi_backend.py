"""WASAPI input through PyAudioWPatch: microphones and loopback capture of system audio."""

from __future__ import annotations

import logging
from typing import Any

from shazam_desktop.audio.backend import AudioStream, FrameCallback, classify_open_error
from shazam_desktop.audio.pcm import downmix_to_mono, frames_from_bytes
from shazam_desktop.audio.sources import (
    AudioSource,
    InputDevice,
    SourceCatalog,
    build_catalog,
    unavailable_catalog,
)
from shazam_desktop.errors import ErrorKind, RecognitionError

log = logging.getLogger(__name__)

_FRAMES_PER_BUFFER = 1024
SYSTEM_HINT = "No output device with WASAPI loopback found."


def _load() -> Any:
    import pyaudiowpatch

    return pyaudiowpatch


def find_default_loopback(
    default_output_name: str, loopbacks: list[dict[str, Any]]
) -> InputDevice | None:
    """Pick the loopback device that mirrors the default output, else the first one."""
    chosen = next(
        (info for info in loopbacks if default_output_name in info["name"]),
        loopbacks[0] if loopbacks else None,
    )
    return None if chosen is None else InputDevice(index=chosen["index"], name=chosen["name"])


class _PyAudioStream:
    def __init__(self, pa: Any, stream: Any, sample_rate: int) -> None:
        self._pa = pa
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
            self._stream.stop_stream()
            self._stream.close()
        except OSError:
            log.warning("Failed to close the input stream cleanly", exc_info=True)
        finally:
            self._pa.terminate()


class WasapiBackend:
    """:class:`~shazam_desktop.audio.backend.AudioBackend` for Windows."""

    def list_sources(self) -> SourceCatalog:
        try:
            pyaudio = _load()
        except ImportError:
            return unavailable_catalog("PyAudioWPatch is not installed.")
        pa = pyaudio.PyAudio()
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            microphones = [
                InputDevice(index=info["index"], name=info["name"])
                for info in (pa.get_device_info_by_index(i) for i in range(pa.get_device_count()))
                if info["hostApi"] == wasapi["index"]
                and info["maxInputChannels"] > 0
                and not info.get("isLoopbackDevice")
            ]
            default_input = int(wasapi["defaultInputDevice"])
            default_output = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            loopback = find_default_loopback(
                default_output["name"], list(pa.get_loopback_device_info_generator())
            )
        except OSError as exc:
            return unavailable_catalog(f"WASAPI unavailable: {exc}")
        finally:
            pa.terminate()

        return build_catalog(
            microphones,
            default_input if default_input >= 0 else None,
            loopback,
            SYSTEM_HINT,
        )

    def open_stream(self, source: AudioSource, on_frames: FrameCallback) -> AudioStream:
        if source.device is None:
            raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, source.label)
        try:
            pyaudio = _load()
        except ImportError as exc:
            raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, str(exc)) from exc

        pa = pyaudio.PyAudio()
        try:
            info = pa.get_device_info_by_index(source.device)
            channels = int(info["maxInputChannels"])
            sample_rate = int(info["defaultSampleRate"])

            def callback(
                in_data: bytes | None, frame_count: int, time_info: Any, status: int
            ) -> tuple[None, int]:
                if in_data:
                    on_frames(downmix_to_mono(frames_from_bytes(in_data, channels)))
                return None, pyaudio.paContinue

            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=source.device,
                frames_per_buffer=_FRAMES_PER_BUFFER,
                stream_callback=callback,
            )
        except OSError as exc:
            pa.terminate()
            raise RecognitionError(classify_open_error(str(exc)), str(exc)) from exc
        return _PyAudioStream(pa, stream, sample_rate)
