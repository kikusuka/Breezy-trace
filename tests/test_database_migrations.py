import sqlite3
from pathlib import Path

import pytest

from breezy_trace.database import SCHEMA_VERSION, connect


def _make_legacy_database(path: Path, version: int) -> None:
    """Create a real current database, then remove objects added after version."""
    connection = connect(path)
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
def test_existing_database_migrates_to_current_schema(
    tmp_path: Path, old_version: int
) -> None:
    path = tmp_path / f"legacy-v{old_version}.sqlite3"
    _make_legacy_database(path, old_version)

    connection = connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
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
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert "language" in columns
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == 0

        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_database_refuses_a_newer_schema(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than this Breezy Trace build"):
        connect(path)
