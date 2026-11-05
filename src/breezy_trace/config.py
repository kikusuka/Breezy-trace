"""Application paths and local configuration."""

from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "Breezy Trace"
APP_AUTHOR = "Breezy Labs"


def data_dir() -> Path:
    """Return the per-user data directory, creating it when needed."""
    path = user_data_path("breezy-trace", "Breezy Labs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    """Return the path to the local registry database."""
    return data_dir() / "trace.sqlite3"
