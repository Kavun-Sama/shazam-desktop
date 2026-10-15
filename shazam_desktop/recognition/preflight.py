"""Startup checks for external tools the Shazam client shells out to."""

from __future__ import annotations

import shutil
from collections.abc import Callable

REQUIRED_BINARIES = ("ffmpeg", "ffprobe")


def ffmpeg_available(which: Callable[[str], str | None] = shutil.which) -> bool:
    """Return whether both ``ffmpeg`` and ``ffprobe`` are on PATH."""
    return all(which(name) is not None for name in REQUIRED_BINARIES)
