"""Entry point: ``python -m shazam_desktop``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from shazam_desktop import __version__
from shazam_desktop.runtime import prepend_bundled_tools_to_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shazam-desktop", description="Music recognizer.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="verify imports, bundled ffmpeg and Qt, then exit with code 0 on success",
    )
    parser.add_argument("--report", type=Path, help="with --self-check: also write the report here")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    # Must precede the first import of pydub (through ShazamAPI), which resolves ffmpeg once.
    prepend_bundled_tools_to_path()
    if args.self_check:
        from shazam_desktop.selfcheck import run_self_check

        return run_self_check(args.report)
    from shazam_desktop.app import run

    return run(sys.argv[:1])


if __name__ == "__main__":
    raise SystemExit(main())
