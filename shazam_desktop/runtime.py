"""Frozen-build helpers: find the bundled ffmpeg and make it visible to child processes."""

from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping
from pathlib import Path

TOOLS_DIR_NAME = "ffmpeg"
HELPER_DIR_NAME = "helper"


def is_frozen() -> bool:
    """Whether the code runs from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundled_tools_dir() -> Path | None:
    """Directory holding the bundled ``ffmpeg`` and ``ffprobe``, or ``None`` outside a bundle."""
    root = getattr(sys, "_MEIPASS", None)
    if not is_frozen() or root is None:
        return None
    directory = Path(root) / TOOLS_DIR_NAME
    return directory if directory.is_dir() else None


def prepend_bundled_tools_to_path(
    environ: MutableMapping[str, str] | None = None,
) -> Path | None:
    """Put the bundled tools first on ``PATH``; call before ``pydub`` is imported.

    ``pydub`` resolves ``ffmpeg`` once, at import time, so this must run before ShazamAPI loads.
    """
    target = os.environ if environ is None else environ
    directory = bundled_tools_dir()
    if directory is None:
        return None
    existing = target.get("PATH", "")
    target["PATH"] = os.pathsep.join(filter(None, (str(directory), existing)))
    return directory


def bundled_helper_dir() -> Path | None:
    """Directory holding the bundled macOS audio helper, or ``None`` outside a bundle."""
    root = getattr(sys, "_MEIPASS", None)
    if not is_frozen() or root is None:
        return None
    directory = Path(root) / HELPER_DIR_NAME
    return directory if directory.is_dir() else None
