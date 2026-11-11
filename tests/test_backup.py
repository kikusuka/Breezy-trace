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


def test_backup_includes_committed_wal_data(tmp_path: Path) -> None:
    live = tmp_path / "live.sqlite3"
    snapshot = tmp_path / "backup.sqlite3"
    make_database(live)

    writer = sqlite3.connect(live)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute(
            "INSERT INTO journal_entries "
            "(id, project_id, title, body, entry_type, created_at, updated_at) "
            "SELECT 'wal-note', id, 'WAL note', 'committed in WAL', 'note', "
            "datetime('now'), datetime('now') FROM projects LIMIT 1"
        )
        writer.commit()
        backup_database(live, snapshot)
    finally:
        writer.close()

    restored = tmp_path / "restored.sqlite3"
    restore_database(snapshot, restored)
    with sqlite3.connect(restored) as connection:
        body = connection.execute(
            "SELECT body FROM journal_entries WHERE id = 'wal-note'"
        ).fetchone()[0]
    assert body == "committed in WAL"


def test_failed_restore_does_not_replace_existing_destination(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.sqlite3"
    sqlite3.connect(invalid).close()
    destination = tmp_path / "live.sqlite3"
    original = b"existing destination must survive"
    destination.write_bytes(original)

    with pytest.raises(ValueError):
        restore_database(invalid, destination)

    assert destination.read_bytes() == original


def test_backup_cleans_temporary_file_when_replace_fails(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.backup as backup_module

    live = tmp_path / "live.sqlite3"
    destination = tmp_path / "backup.sqlite3"
    make_database(live)
    destination.write_bytes(b"previous backup")

    def fail_replace(_source, _destination):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(backup_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        backup_database(live, destination)

    assert destination.read_bytes() == b"previous backup"
    assert list(tmp_path.glob("backup.sqlite3.*.backup")) == []


def test_backup_handles_uri_special_characters_in_paths(tmp_path: Path) -> None:
    live = tmp_path / "live # database.sqlite3"
    snapshot = tmp_path / "backup # database.sqlite3"
    restored = tmp_path / "restored # database.sqlite3"
    make_database(live)

    backup_database(live, snapshot)
    restore_database(snapshot, restored)

    projects = ProjectRegistry(restored).list_projects()
    assert len(projects) == 1


def test_restore_refuses_database_with_wal_sidecars(tmp_path: Path) -> None:
    backup = tmp_path / "backup.sqlite3"
    destination = tmp_path / "live.sqlite3"
    make_database(backup)
    destination.write_bytes(b"existing live database")
    wal = Path(f"{destination}-wal")
    wal.write_bytes(b"active WAL marker")

    with pytest.raises(RuntimeError, match="Close every Breezy Trace process"):
        restore_database(backup, destination)

    assert destination.read_bytes() == b"existing live database"
    assert wal.read_bytes() == b"active WAL marker"
