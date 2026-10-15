"""Recognition result model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Track:
    """A recognized track; every field may be absent in the upstream response."""

    title: str | None
    artist: str | None
    cover_url: str | None
