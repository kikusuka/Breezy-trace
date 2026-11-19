"""PyInstaller entry point for the standalone Breezy Trace binaries."""

from breezy_trace.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
