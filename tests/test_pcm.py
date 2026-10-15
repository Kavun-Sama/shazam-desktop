from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from shazam_desktop.audio.pcm import (
    Int16Array,
    downmix_to_mono,
    frames_from_bytes,
    pcm_to_wav,
    rms_level,
)


def test_downmix_averages_channels() -> None:
    stereo: Int16Array = np.array([[100, 300], [-200, 0], [10, 11]], dtype=np.int16)
    assert downmix_to_mono(stereo).tolist() == [200, -100, 10]


def test_downmix_of_mono_copies_the_input() -> None:
    mono: Int16Array = np.array([[1], [2], [3]], dtype=np.int16)
    result = downmix_to_mono(mono)
    result[0] = 99
    assert result.tolist() == [99, 2, 3]
    assert mono[0, 0] == 1


def test_downmix_rejects_flat_arrays() -> None:
    with pytest.raises(ValueError, match="frames, channels"):
        downmix_to_mono(np.zeros(4, dtype=np.int16))


def test_frames_from_bytes_deinterleaves() -> None:
    data = np.array([1, 2, 3, 4, 5, 6], dtype=np.int16).tobytes()
    assert frames_from_bytes(data, 2).tolist() == [[1, 2], [3, 4], [5, 6]]


def test_silence_is_zero_and_full_scale_is_one() -> None:
    assert rms_level(np.zeros(256, dtype=np.int16)) == 0.0
    assert rms_level(np.full(256, 32767, dtype=np.int16)) == 1.0
    assert rms_level(np.zeros(0, dtype=np.int16)) == 0.0


def test_level_grows_monotonically_with_amplitude() -> None:
    levels = [
        rms_level(np.full(256, amplitude, dtype=np.int16)) for amplitude in (100, 1000, 5000, 20000)
    ]
    assert levels == sorted(levels)
    assert 0.0 < levels[0] < levels[-1] <= 1.0


def test_wav_round_trip_keeps_rate_and_samples() -> None:
    pcm = np.arange(-50, 50, dtype=np.int16).tobytes()
    with wave.open(io.BytesIO(pcm_to_wav(pcm, 44100)), "rb") as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (
            1,
            2,
            44100,
        )
        assert reader.readframes(reader.getnframes()) == pcm
