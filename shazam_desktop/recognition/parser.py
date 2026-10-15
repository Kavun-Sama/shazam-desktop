"""Extraction of a :class:`Track` from a raw Shazam response."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from shazam_desktop.recognition.models import Track

_COVER_KEYS = ("coverart", "background")


def parse_response(response: object) -> Track | None:
    """Return the track for a response that contains a match, otherwise ``None``.

    A response counts as a match only when ``matches`` is a non-empty list and
    ``track`` is an object. Individual track fields are optional.
    """
    if not isinstance(response, Mapping):
        return None
    matches = response.get("matches")
    if not isinstance(matches, Sequence) or isinstance(matches, str | bytes) or not matches:
        return None
    track = response.get("track")
    if not isinstance(track, Mapping):
        return None
    return Track(
        title=_text(track.get("title")),
        artist=_text(track.get("subtitle")),
        cover_url=_cover_url(track.get("images")),
    )


def _cover_url(images: object) -> str | None:
    if not isinstance(images, Mapping):
        return None
    for key in _COVER_KEYS:
        url = _text(images.get(key))
        if url is not None:
            return url
    return None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
