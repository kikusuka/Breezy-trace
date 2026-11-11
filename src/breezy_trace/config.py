"""Application paths and local configuration."""

import os
from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "Breezy Trace"
APP_AUTHOR = "Breezy Labs"


def data_dir() -> Path:
    """Return the per-user data directory, creating it when needed.

    ``BREEZY_TRACE_DATA_DIR`` can point the application and tests at a
    separate data folder without touching the user's real database.
    """
    override = os.environ.get("BREEZY_TRACE_DATA_DIR")
    path = Path(override).expanduser() if override else user_data_path("breezy-trace", "Breezy Labs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    """Return the path to the local registry database."""
    return data_dir() / "trace.sqlite3"
