"""Portable, validated SQLite backup and restore helpers."""

import os
import sqlite3
import tempfile
from pathlib import Path

from breezy_trace.database import SCHEMA_VERSION


def backup_database(source: Path, destination: Path) -> Path:
    """Create a consistent SQLite backup, including committed WAL contents."""
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if source == destination:
        raise ValueError("Backup destination must differ from the live database.")
    if not source.is_file():
        raise FileNotFoundError(f"Database does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
            with sqlite3.connect(temporary) as dst:
                src.backup(dst)
                result = dst.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise ValueError(f"Database integrity check failed: {result}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_database(backup: Path, destination: Path) -> Path:
    """Restore a validated backup atomically; caller must confirm overwrite."""
    backup = backup.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if backup == destination:
        raise ValueError("Backup source and live database destination must differ.")
    if not backup.is_file():
        raise FileNotFoundError(f"Backup file does not exist: {backup}")
    with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as source:
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        version = source.execute("PRAGMA user_version").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Backup integrity check failed: {integrity}")
        if version < 1 or version > SCHEMA_VERSION:
            raise ValueError(f"Unsupported backup schema version: {version}")
        required = {"projects", "journal_entries", "project_tasks", "project_decisions"}
        actual = {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not required.issubset(actual):
            raise ValueError("File is not a complete Breezy Trace database.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=destination.name + ".", suffix=".restore", dir=destination.parent
        )
        os.close(fd)
        temporary = Path(temp_name)
        try:
            with sqlite3.connect(temporary) as target:
                source.backup(target)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination
