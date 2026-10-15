"""The only module that touches the unofficial ShazamAPI client."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import closing
from typing import Any

import requests
from ShazamAPI import Shazam

from shazam_desktop.errors import ErrorKind, RecognitionError
from shazam_desktop.recognition.models import Track
from shazam_desktop.recognition.parser import parse_response

log = logging.getLogger(__name__)


class _ObservedShazam(Shazam):
    """Reports the moment the first signature is about to be sent.

    Everything before it (audio decoding and signature generation) is
    "fingerprinting"; the request itself is "matching".
    """

    def __init__(self, song_data: bytes, on_request: Callable[[], None]) -> None:
        super().__init__(song_data)
        self._on_request = on_request
        self._requested = False

    def sendRecognizeRequest(self, sig: Any) -> Any:
        if not self._requested:
            self._requested = True
            self._on_request()
        return super().sendRecognizeRequest(sig)


class ShazamRecognizer:
    """:class:`~shazam_desktop.recognition.recognizer.Recognizer` backed by ShazamAPI."""

    def recognize(self, wav: bytes, *, on_matching: Callable[[], None]) -> Track | None:
        shazam = _ObservedShazam(wav, on_matching)
        try:
            with closing(shazam.recognizeSong()) as responses:
                for _offset, response in responses:
                    track = parse_response(response)
                    if track is not None:
                        return track
        except FileNotFoundError as exc:
            # pydub shells out to ffmpeg/ffprobe and surfaces a missing binary this way.
            raise RecognitionError(ErrorKind.FFMPEG_MISSING, str(exc)) from exc
        except requests.RequestException as exc:
            raise RecognitionError(ErrorKind.NETWORK, str(exc)) from exc
        except Exception as exc:
            # The client is reverse-engineered and untyped: anything it raises is unexpected.
            log.exception("Shazam client failed")
            raise RecognitionError(ErrorKind.UNEXPECTED, repr(exc)) from exc
        return None
