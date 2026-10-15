from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
import requests

from shazam_desktop.errors import ErrorKind, RecognitionError
from shazam_desktop.recognition.models import Track
from shazam_desktop.recognition.shazam import ShazamRecognizer


class _Signature:
    number_samples = 64000
    sample_rate_hz = 16000

    def encode_to_uri(self) -> str:
        return "data:audio/vnd.shazam.sig;base64,AAAA"


class _SignatureGenerator:
    def __init__(self, count: int) -> None:
        self._remaining = count
        self.samples_processed = 0

    def get_next_signature(self) -> _Signature | None:
        if self._remaining == 0:
            return None
        self._remaining -= 1
        self.samples_processed += 128000
        return _Signature()


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace only what needs ffmpeg or the network; the library's own flow still runs."""
    from ShazamAPI import Shazam

    state = SimpleNamespace(signatures=2, replies=[], posts=0)

    monkeypatch.setattr(Shazam, "normalizateAudioData", lambda self, data: object())
    monkeypatch.setattr(
        Shazam,
        "createSignatureGenerator",
        lambda self, audio: _SignatureGenerator(state.signatures),
    )

    def post(url: str, **kwargs: Any) -> _Response:
        reply = state.replies[min(state.posts, len(state.replies) - 1)]
        state.posts += 1
        if isinstance(reply, Exception):
            raise reply
        return _Response(reply)

    monkeypatch.setattr(requests, "post", post)
    return state


def recognize(matching_calls: list[int] | None = None) -> Track | None:
    calls = matching_calls if matching_calls is not None else []
    return ShazamRecognizer().recognize(b"wav", on_matching=lambda: calls.append(1))


def test_first_matching_response_ends_the_run(
    client: SimpleNamespace, match_response: dict[str, Any], no_match_response: dict[str, Any]
) -> None:
    client.replies = [match_response, no_match_response]
    calls: list[int] = []

    track = recognize(calls)

    assert track == Track(
        "Neon Harbor",
        "The Paper Satellites",
        "https://images.example.com/cover/400x400/neon-harbor.jpg",
    )
    assert client.posts == 1
    assert calls == [1]


def test_later_response_can_carry_the_match(
    client: SimpleNamespace, match_response: dict[str, Any], no_match_response: dict[str, Any]
) -> None:
    client.replies = [no_match_response, match_response]
    calls: list[int] = []

    assert recognize(calls) is not None
    assert client.posts == 2
    assert calls == [1]


def test_no_match_in_any_response(
    client: SimpleNamespace, no_match_response: dict[str, Any]
) -> None:
    client.replies = [no_match_response]
    assert recognize() is None
    assert client.posts == 2


def test_connection_failure_is_a_network_error(client: SimpleNamespace) -> None:
    client.replies = [requests.ConnectionError("offline")]
    with pytest.raises(RecognitionError) as raised:
        recognize()
    assert raised.value.kind is ErrorKind.NETWORK


def test_non_json_reply_is_a_network_error(client: SimpleNamespace) -> None:
    client.replies = [requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)]
    with pytest.raises(RecognitionError) as raised:
        recognize()
    assert raised.value.kind is ErrorKind.NETWORK


def test_missing_ffmpeg_is_reported_before_any_request(
    monkeypatch: pytest.MonkeyPatch, client: SimpleNamespace
) -> None:
    from ShazamAPI import Shazam

    def no_ffprobe(self: Shazam, data: bytes) -> None:
        raise FileNotFoundError(2, "No such file or directory", "ffprobe")

    monkeypatch.setattr(Shazam, "normalizateAudioData", no_ffprobe)
    calls: list[int] = []

    with pytest.raises(RecognitionError) as raised:
        recognize(calls)

    assert raised.value.kind is ErrorKind.FFMPEG_MISSING
    assert calls == []
    assert client.posts == 0


def test_unexpected_library_failure_is_wrapped(client: SimpleNamespace) -> None:
    client.replies = [KeyError("boom")]
    with pytest.raises(RecognitionError) as raised:
        recognize()
    assert raised.value.kind is ErrorKind.UNEXPECTED


def test_real_client_without_ffmpeg_reports_ffmpeg_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RecognitionError) as raised:
        recognize()
    assert raised.value.kind is ErrorKind.FFMPEG_MISSING
