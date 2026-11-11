import sqlite3
from pathlib import Path

import pytest

from breezy_trace.database import SCHEMA_VERSION, connect


def _make_legacy_database(path: Path, version: int) -> None:
    """Create a populated current database, then remove later schema objects."""
    connection = connect(path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO projects (id, name, path, registered_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "project-1",
                    "preserved",
                    str(path.parent / "preserved-project"),
                    "2026-01-01T00:00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO journal_entries
                    (id, project_id, title, body, entry_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "note-1",
                    "project-1",
                    "Keep this",
                    "Original journal data",
                    "note",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )
    finally:
        connection.close()

    with sqlite3.connect(path) as connection:
        if version < 4:
            connection.execute("DROP INDEX idx_code_symbols_project_language")
            connection.execute("DROP INDEX idx_code_imports_project_language")
            for table in ("code_indexed_files", "code_symbols", "code_imports"):
                connection.execute(f"ALTER TABLE {table} DROP COLUMN language")
        if version < 3:
            for table in ("code_indexed_files", "code_symbols", "code_imports"):
                connection.execute(f"DROP TABLE {table}")
        if version < 2:
            connection.execute("DROP TABLE file_activity_state")
        connection.execute(f"PRAGMA user_version = {version}")


@pytest.mark.parametrize("old_version", [1, 2, 3])
def test_existing_database_migrates_to_current_schema(tmp_path: Path, old_version: int) -> None:
    path = tmp_path / f"legacy-v{old_version}.sqlite3"
    _make_legacy_database(path, old_version)

    connection = connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "projects",
            "journal_entries",
            "project_tasks",
            "project_decisions",
            "agent_sessions",
            "session_events",
            "file_events",
            "commits",
            "remote_snapshots",
            "file_activity_state",
            "code_indexed_files",
            "code_symbols",
            "code_imports",
        }.issubset(tables)

        for table in ("code_indexed_files", "code_symbols", "code_imports"):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert "language" in columns
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

        assert (
            connection.execute("SELECT name FROM projects WHERE id = 'project-1'").fetchone()[0]
            == "preserved"
        )
        assert (
            connection.execute("SELECT body FROM journal_entries WHERE id = 'note-1'").fetchone()[0]
            == "Original journal data"
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_database_refuses_a_newer_schema(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than this Breezy Trace build"):
        connect(path)


def test_connect_closes_handle_when_schema_is_newer(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.database as database_module

    path = tmp_path / "future-schema.sqlite3"
    with sqlite3.connect(path) as setup:
        setup.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    original_connect = sqlite3.connect
    opened = []

    def tracking_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(database_module.sqlite3, "connect", tracking_connect)
    with pytest.raises(RuntimeError, match="newer than this Breezy Trace build"):
        database_module.connect(path)

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
