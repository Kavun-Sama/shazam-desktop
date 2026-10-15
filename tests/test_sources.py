from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar

import numpy as np
import pytest

from shazam_desktop.audio.backend import classify_open_error
from shazam_desktop.audio.backends import sounddevice_backend, wasapi_backend
from shazam_desktop.audio.sources import (
    DEFAULT_MIC_KEY,
    SYSTEM_KEY,
    InputDevice,
    SourceKind,
    build_catalog,
    unavailable_catalog,
)
from shazam_desktop.errors import ErrorKind, RecognitionError

HINT = "route output somewhere"


def test_catalog_lists_default_mic_devices_then_system_audio() -> None:
    catalog = build_catalog(
        [InputDevice(3, "USB Mic"), InputDevice(5, "Line In")],
        default_index=3,
        loopback=InputDevice(7, "Loopback Audio 2ch"),
        system_hint=HINT,
    )
    assert [s.key for s in catalog.sources] == [
        DEFAULT_MIC_KEY,
        "mic:USB Mic",
        "mic:Line In",
        SYSTEM_KEY,
    ]
    assert catalog.sources[0].label == "Microphone"
    assert catalog.find(DEFAULT_MIC_KEY).device == 3  # type: ignore[union-attr]
    system = catalog.system
    assert system is not None
    assert (system.available, system.hint, system.device) == (True, None, 7)


def test_system_audio_is_disabled_with_a_hint_without_loopback() -> None:
    catalog = build_catalog([InputDevice(1, "Mic")], 1, None, HINT)
    system = catalog.system
    assert system is not None
    assert (system.available, system.hint, system.device) == (False, HINT, None)


def test_duplicate_device_names_get_distinct_keys() -> None:
    catalog = build_catalog([InputDevice(1, "Mic"), InputDevice(2, "Mic")], 1, None, HINT)
    assert [s.key for s in catalog.microphones] == [DEFAULT_MIC_KEY, "mic:Mic", "mic:Mic (2)"]


def test_missing_default_input_disables_the_default_microphone() -> None:
    catalog = build_catalog([], None, None, HINT)
    default = catalog.find(DEFAULT_MIC_KEY)
    assert default is not None
    assert (default.available, default.hint) == (False, "No input device found.")


def test_resolve_falls_back_to_default_microphone_for_unknown_keys() -> None:
    catalog = build_catalog([InputDevice(1, "Mic")], 1, None, HINT)
    resolved = catalog.resolve("mic:Unplugged")
    assert resolved is not None
    assert resolved.key == DEFAULT_MIC_KEY
    assert catalog.resolve(SYSTEM_KEY) is catalog.system


def test_unavailable_catalog_carries_the_reason() -> None:
    catalog = unavailable_catalog("no backend")
    assert all(not s.available for s in catalog.sources)
    assert catalog.system is not None
    assert catalog.system.hint == "no backend"


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("Error opening InputStream: Access is denied.", ErrorKind.PERMISSION_DENIED),
        ("Microphone permission was refused", ErrorKind.PERMISSION_DENIED),
        ("Invalid device", ErrorKind.SOURCE_UNAVAILABLE),
    ],
)
def test_open_errors_are_classified(message: str, kind: ErrorKind) -> None:
    assert classify_open_error(message) is kind


# --- sounddevice backend ---------------------------------------------------------------------


class _PortAudioError(Exception):
    pass


def _device(index: int, name: str, inputs: int, rate: float = 48000.0) -> dict[str, Any]:
    return {
        "name": name,
        "index": index,
        "max_input_channels": inputs,
        "default_samplerate": rate,
    }


class _FakeInputStream:
    instances: ClassVar[list[_FakeInputStream]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started = False
        self.closed = False
        _FakeInputStream.instances.append(self)

    def start(self) -> None:
        self.started = True
        frames = np.full((4, self.kwargs["channels"]), 1000, dtype=np.int16)
        self.kwargs["callback"](frames, 4, None, None)

    def stop(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _fake_sd(devices: list[dict[str, Any]], default: int | None) -> SimpleNamespace:
    def query_devices(device: int | None = None, kind: str | None = None) -> Any:
        if kind == "input":
            if default is None:
                raise ValueError("No input device matching 'input'")
            return devices[default]
        if device is None:
            return devices
        return devices[device]

    return SimpleNamespace(
        query_devices=query_devices,
        PortAudioError=_PortAudioError,
        InputStream=_FakeInputStream,
    )


@pytest.fixture
def macos_devices() -> list[dict[str, Any]]:
    return [
        _device(0, "MacBook Pro Speakers", 0),
        _device(1, "MacBook Pro Microphone", 1),
        _device(2, "Monitor of Built-in Audio", 2),
        _device(3, "USB Mic", 1, 44100.0),
    ]


def test_sounddevice_backend_builds_catalog_from_found_devices(
    monkeypatch: pytest.MonkeyPatch, macos_devices: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(sounddevice_backend, "_load", lambda: _fake_sd(macos_devices, default=1))
    catalog = sounddevice_backend.SoundDeviceBackend().list_sources()

    assert [s.label for s in catalog.microphones] == [
        "Microphone",
        "MacBook Pro Microphone",
        "USB Mic",
    ]
    assert catalog.find(DEFAULT_MIC_KEY).device == 1  # type: ignore[union-attr]
    system = catalog.system
    assert system is not None
    assert (system.available, system.device) == (True, 2)


def test_sounddevice_backend_without_loopback_disables_system_audio(
    monkeypatch: pytest.MonkeyPatch, macos_devices: list[dict[str, Any]]
) -> None:
    plain = [d for d in macos_devices if "Monitor" not in d["name"]]
    monkeypatch.setattr(sounddevice_backend, "_load", lambda: _fake_sd(plain, default=1))
    system = sounddevice_backend.SoundDeviceBackend().list_sources().system
    assert system is not None
    assert not system.available
    assert system.hint == sounddevice_backend.SYSTEM_HINT


def test_sounddevice_backend_survives_a_missing_portaudio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Any:
        raise OSError("PortAudio library not found")

    monkeypatch.setattr(sounddevice_backend, "_load", broken)
    catalog = sounddevice_backend.SoundDeviceBackend().list_sources()
    assert all(not s.available for s in catalog.sources)
    assert catalog.system is not None
    assert catalog.system.hint is not None
    assert "PortAudio" in catalog.system.hint


def test_sounddevice_stream_downmixes_to_mono_at_the_device_rate(
    monkeypatch: pytest.MonkeyPatch, macos_devices: list[dict[str, Any]]
) -> None:
    _FakeInputStream.instances.clear()
    monkeypatch.setattr(sounddevice_backend, "_load", lambda: _fake_sd(macos_devices, default=1))
    backend = sounddevice_backend.SoundDeviceBackend()
    source = backend.list_sources().system
    assert source is not None

    received: list[Any] = []
    stream = backend.open_stream(source, received.append)

    assert stream.sample_rate == 48000
    assert received[0].shape == (4,)
    assert received[0].tolist() == [1000] * 4
    opened = _FakeInputStream.instances[0]
    assert opened.kwargs["channels"] == 2
    assert opened.kwargs["dtype"] == "int16"
    stream.close()
    assert opened.closed


def test_sounddevice_open_error_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    class Denying(_FakeInputStream):
        def __init__(self, **kwargs: Any) -> None:
            raise _PortAudioError("Access denied by the system")

    fake = _fake_sd([_device(0, "Mic", 1)], default=0)
    fake.InputStream = Denying
    monkeypatch.setattr(sounddevice_backend, "_load", lambda: fake)
    backend = sounddevice_backend.SoundDeviceBackend()
    mic = backend.list_sources().find(DEFAULT_MIC_KEY)
    assert mic is not None
    with pytest.raises(RecognitionError) as raised:
        backend.open_stream(mic, lambda _: None)
    assert raised.value.kind is ErrorKind.PERMISSION_DENIED


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Soundflower (2ch)", True),
        ("Loopback Audio", True),
        ("Monitor of Built-in Audio", True),
        ("MacBook Pro Microphone", False),
    ],
)
def test_loopback_detection_by_name(name: str, expected: bool) -> None:
    assert sounddevice_backend.is_loopback_name(name) is expected


# --- WASAPI backend --------------------------------------------------------------------------


class _FakePyAudioInstance:
    terminated = 0

    def __init__(self, loopbacks: list[dict[str, Any]]) -> None:
        self._loopbacks = loopbacks
        self._devices = [
            {"index": 0, "name": "Speakers (Realtek)", "hostApi": 0, "maxInputChannels": 0},
            {"index": 1, "name": "Microphone (Realtek)", "hostApi": 0, "maxInputChannels": 2},
            {"index": 2, "name": "Headset (USB)", "hostApi": 0, "maxInputChannels": 1},
            {"index": 3, "name": "Old MME Mic", "hostApi": 1, "maxInputChannels": 2},
            *self._loopbacks,
        ]

    def get_host_api_info_by_type(self, kind: int) -> dict[str, Any]:
        return {"index": 0, "defaultInputDevice": 1, "defaultOutputDevice": 0}

    def get_device_count(self) -> int:
        return len(self._devices)

    def get_device_info_by_index(self, index: int) -> dict[str, Any]:
        return self._devices[index]

    def get_loopback_device_info_generator(self) -> Any:
        yield from self._loopbacks

    def terminate(self) -> None:
        _FakePyAudioInstance.terminated += 1


def _fake_pyaudio(loopbacks: list[dict[str, Any]]) -> SimpleNamespace:
    return SimpleNamespace(
        PyAudio=lambda: _FakePyAudioInstance(loopbacks),
        paWASAPI=13,
        paInt16=8,
        paContinue=0,
    )


_SPEAKER_LOOPBACK = {
    "index": 4,
    "name": "Speakers (Realtek) [Loopback]",
    "hostApi": 0,
    "maxInputChannels": 2,
    "isLoopbackDevice": True,
}


def test_wasapi_lists_only_wasapi_microphones_and_a_default_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wasapi_backend, "_load", lambda: _fake_pyaudio([_SPEAKER_LOOPBACK]))
    catalog = wasapi_backend.WasapiBackend().list_sources()

    assert [s.label for s in catalog.microphones] == [
        "Microphone",
        "Microphone (Realtek)",
        "Headset (USB)",
    ]
    system = catalog.system
    assert system is not None
    assert (system.available, system.device) == (True, 4)
    assert system.kind is SourceKind.SYSTEM


def test_wasapi_without_loopback_disables_system_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wasapi_backend, "_load", lambda: _fake_pyaudio([]))
    system = wasapi_backend.WasapiBackend().list_sources().system
    assert system is not None
    assert not system.available


def test_wasapi_releases_portaudio_after_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakePyAudioInstance.terminated = 0
    monkeypatch.setattr(wasapi_backend, "_load", lambda: _fake_pyaudio([_SPEAKER_LOOPBACK]))
    wasapi_backend.WasapiBackend().list_sources()
    assert _FakePyAudioInstance.terminated == 1


def test_wasapi_without_the_package_reports_it(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> Any:
        raise ImportError("pyaudiowpatch")

    monkeypatch.setattr(wasapi_backend, "_load", missing)
    catalog = wasapi_backend.WasapiBackend().list_sources()
    assert all(not s.available for s in catalog.sources)


def test_default_loopback_prefers_the_default_output() -> None:
    other = {**_SPEAKER_LOOPBACK, "index": 9, "name": "Headphones [Loopback]"}
    chosen = wasapi_backend.find_default_loopback("Speakers (Realtek)", [other, _SPEAKER_LOOPBACK])
    assert chosen == InputDevice(4, "Speakers (Realtek) [Loopback]")
    assert wasapi_backend.find_default_loopback("Unknown", [other]) == InputDevice(
        9, "Headphones [Loopback]"
    )
    assert wasapi_backend.find_default_loopback("Unknown", []) is None
