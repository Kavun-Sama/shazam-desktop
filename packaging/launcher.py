"""PyInstaller entry script (the spec needs a file, not ``-m``)."""

from shazam_desktop.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
