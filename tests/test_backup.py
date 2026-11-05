import sqlite3
import subprocess
from pathlib import Path

import pytest

from breezy_trace.backup import backup_database, restore_database
from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry


def make_database(path: Path) -> None:
    repo = path.parent / "project"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    project = ProjectRegistry(path).register(repo)
    JournalStore(path).add_note(project, "Keep me", "Backup content")


def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    live = tmp_path / "live.sqlite3"
    snapshot = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    make_database(live)

    backup_database(live, snapshot)
    restore_database(snapshot, restored)

    projects = ProjectRegistry(restored).list_projects()
    assert len(projects) == 1
    assert JournalStore(restored).list_entries(projects[0])[0]["body"] == "Backup content"


def test_restore_rejects_non_trace_database(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.sqlite3"
    sqlite3.connect(invalid).close()

    with pytest.raises(ValueError, match="schema version"):
        restore_database(invalid, tmp_path / "restored.sqlite3")


def test_backup_rejects_same_path(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    make_database(db)
    with pytest.raises(ValueError, match="differ"):
        backup_database(db, db)
