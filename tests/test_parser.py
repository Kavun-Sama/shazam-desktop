from __future__ import annotations

import copy
from typing import Any

import pytest

from shazam_desktop.recognition.models import Track
from shazam_desktop.recognition.parser import parse_response


def test_parses_full_match(match_response: dict[str, Any]) -> None:
    assert parse_response(match_response) == Track(
        title="Neon Harbor",
        artist="The Paper Satellites",
        cover_url="https://images.example.com/cover/400x400/neon-harbor.jpg",
    )


def test_empty_matches_is_not_a_match(no_match_response: dict[str, Any]) -> None:
    assert parse_response(no_match_response) is None


def test_falls_back_to_background_when_coverart_is_missing(match_response: dict[str, Any]) -> None:
    del match_response["track"]["images"]["coverart"]
    track = parse_response(match_response)
    assert track is not None
    assert track.cover_url == "https://images.example.com/background/neon-harbor.jpg"


def test_no_images_leaves_cover_empty(match_response: dict[str, Any]) -> None:
    del match_response["track"]["images"]
    track = parse_response(match_response)
    assert track is not None
    assert track.cover_url is None


def test_missing_subtitle_leaves_artist_empty(match_response: dict[str, Any]) -> None:
    del match_response["track"]["subtitle"]
    track = parse_response(match_response)
    assert track is not None
    assert (track.title, track.artist) == ("Neon Harbor", None)


def test_missing_title_leaves_title_empty(match_response: dict[str, Any]) -> None:
    del match_response["track"]["title"]
    track = parse_response(match_response)
    assert track is not None
    assert (track.title, track.artist) == (None, "The Paper Satellites")


def test_blank_strings_are_treated_as_absent(match_response: dict[str, Any]) -> None:
    match_response["track"]["title"] = "   "
    match_response["track"]["images"]["coverart"] = ""
    track = parse_response(match_response)
    assert track is not None
    assert track.title is None
    assert track.cover_url == "https://images.example.com/background/neon-harbor.jpg"


def test_surrounding_whitespace_is_stripped(match_response: dict[str, Any]) -> None:
    match_response["track"]["title"] = "  Neon Harbor \n"
    track = parse_response(match_response)
    assert track is not None
    assert track.title == "Neon Harbor"


@pytest.mark.parametrize(
    "response",
    [
        None,
        "matches",
        [],
        {},
        {"matches": None},
        {"matches": "x", "track": {"title": "t"}},
        {"matches": {"id": "1"}, "track": {"title": "t"}},
    ],
)
def test_malformed_responses_are_not_matches(response: object) -> None:
    assert parse_response(response) is None


def test_match_without_track_is_not_usable(match_response: dict[str, Any]) -> None:
    del match_response["track"]
    assert parse_response(match_response) is None


def test_non_string_fields_are_ignored(match_response: dict[str, Any]) -> None:
    match_response["track"]["title"] = 42
    match_response["track"]["subtitle"] = ["a"]
    match_response["track"]["images"] = "none"
    track = parse_response(match_response)
    assert track == Track(title=None, artist=None, cover_url=None)


def test_parser_does_not_mutate_input(match_response: dict[str, Any]) -> None:
    snapshot = copy.deepcopy(match_response)
    parse_response(match_response)
    assert match_response == snapshot
