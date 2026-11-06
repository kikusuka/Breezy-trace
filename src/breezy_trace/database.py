"""SQLite storage and schema migrations for Breezy Trace."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    registered_at TEXT NOT NULL,
    last_opened_at TEXT
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    entry_type TEXT NOT NULL DEFAULT 'note',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS project_decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    external_id TEXT,
    started_at TEXT,
    ended_at TEXT,
    source TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS session_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS file_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES agent_sessions(id) ON DELETE SET NULL,
    path TEXT NOT NULL,
    event_type TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    evidence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commits (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sha TEXT NOT NULL,
    branch TEXT,
    committed_at TEXT,
    subject TEXT NOT NULL,
    PRIMARY KEY (project_id, sha)
);

CREATE TABLE IF NOT EXISTS remote_snapshots (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    remote_name TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_journal_project_created
    ON journal_entries(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status
    ON project_tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sessions_project_started
    ON agent_sessions(project_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_file_events_project_observed
    ON file_events(project_id, observed_at DESC);
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open a configured SQLite connection and ensure the schema exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        connection.close()
        raise RuntimeError(
            f"Database schema version {version} is newer than this Breezy Trace build "
            f"supports ({SCHEMA_VERSION})."
        )
    if version < 1:
        with connection:
            connection.executescript(_SCHEMA)
            connection.execute("PRAGMA user_version = 1")
        version = 1
    if version < 2:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS file_activity_state (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    status_code TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, path)
                );
                CREATE INDEX IF NOT EXISTS idx_file_activity_state_project
                    ON file_activity_state(project_id);
                """
            )
            connection.execute("PRAGMA user_version = 2")
    if version < 3:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS code_indexed_files (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    parse_error TEXT,
                    PRIMARY KEY (project_id, path)
                );
                CREATE TABLE IF NOT EXISTS code_symbols (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    qualified_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS code_imports (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    module TEXT NOT NULL,
                    line INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_code_symbols_project_name
                    ON code_symbols(project_id, name);
                CREATE INDEX IF NOT EXISTS idx_code_symbols_project_path
                    ON code_symbols(project_id, path, line);
                CREATE INDEX IF NOT EXISTS idx_code_imports_project_module
                    ON code_imports(project_id, module);
                """
            )
            connection.execute("PRAGMA user_version = 3")
    return connection
