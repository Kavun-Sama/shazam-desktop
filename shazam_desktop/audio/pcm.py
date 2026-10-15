"""PCM helpers: channel downmix, level metering and in-memory WAV encoding."""

from __future__ import annotations

import io
import math
import wave

import numpy as np
import numpy.typing as npt

Int16Array = npt.NDArray[np.int16]

_FLOOR_DB = -60.0
_CEILING_DB = -10.0
_FULL_SCALE = 32768.0


def frames_from_bytes(data: bytes, channels: int) -> Int16Array:
    """Interpret interleaved int16 bytes as a ``(frames, channels)`` array."""
    return np.frombuffer(data, dtype=np.int16).reshape(-1, channels)


def downmix_to_mono(frames: Int16Array) -> Int16Array:
    """Average the channels of a ``(frames, channels)`` array into mono."""
    if frames.ndim != 2:
        raise ValueError("expected a (frames, channels) array")
    if frames.shape[1] == 1:
        return frames[:, 0].copy()
    return frames.mean(axis=1).astype(np.int16)


def rms_level(samples: Int16Array) -> float:
    """Map the RMS of ``samples`` to a 0..1 meter value on a -60..-10 dBFS scale."""
    if samples.size == 0:
        return 0.0
    normalized = samples.astype(np.float32) / _FULL_SCALE
    rms = float(np.sqrt(np.mean(normalized * normalized)))
    if rms <= 0.0:
        return 0.0
    decibels = 20.0 * math.log10(rms)
    return min(1.0, max(0.0, (decibels - _FLOOR_DB) / (_CEILING_DB - _FLOOR_DB)))


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap mono 16-bit PCM in a WAV container, entirely in memory."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm)
    return buffer.getvalue()
