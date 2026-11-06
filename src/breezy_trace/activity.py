"""Explicit, metadata-only snapshots of Git working-tree file activity.

This module records paths and Git status codes only. It never opens file contents,
starts a watcher, or attributes changes to an agent session.
"""

import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from contextlib import closing

from breezy_trace.database import connect
from breezy_trace.models import Project


def _decode_path(value: bytes) -> str:
    """Decode a Git path for SQLite without losing scan stability on odd filenames."""
    return value.decode("utf-8", errors="replace")


def _parse_porcelain(data: bytes) -> dict[str, tuple[str, str]]:
    """Parse NUL-delimited porcelain v1 output, including rename/copy extra fields."""
    tokens = data.split(b"\0")
    current: dict[str, tuple[str, str]] = {}
    index = 0
    while index < len(tokens):
        record = tokens[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            continue
        status = record[:2].decode("ascii", errors="replace")
        path = _decode_path(record[3:])
        if "R" in status or "C" in status:
            # In -z mode Git emits the destination first, then the original path.
            index += 1
        if path:
            current[path] = (status, _event_type(status))
    return current


def _event_type(status: str) -> str:
    if any(code in status for code in ("U",)) or status in {"AA", "DD"}:
        return "conflicted"
    if "R" in status or "C" in status:
        return "renamed"
    if "D" in status:
        return "deleted"
    if "?" in status:
        return "untracked"
    if status[0] != " " and status[1] != " ":
        return "staged_and_modified"
    if status[0] != " ":
        return "staged"
    return "modified"


class FileActivityStore:
    """Store explicit Git working-tree snapshots and only emit state transitions."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def scan(self, project: Project) -> dict[str, int]:
        """Take one read-only Git status snapshot for a registered project."""
        result = subprocess.run(
            [
                "git", "-C", project.path, "status", "--porcelain=v1", "-z",
                "--untracked-files=all",
            ],
            capture_output=True,
            check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or "Git status could not be read for this project.")

        snapshot = _parse_porcelain(result.stdout)
        observed_at = datetime.now(UTC).isoformat()
        events_created = 0
        with closing(connect(self.db_path)) as connection, connection:
            exists = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
            if not exists:
                raise ValueError("Project is not registered in this Breezy Trace database.")

            previous_rows = connection.execute(
                "SELECT path, status_code FROM file_activity_state WHERE project_id = ?",
                (project.id,),
            ).fetchall()
            previous = {row["path"]: row["status_code"] for row in previous_rows}

            for path, (status_code, event_type) in snapshot.items():
                if previous.get(path) == status_code:
                    continue
                connection.execute(
                    """
                    INSERT INTO file_events
                    (id, project_id, session_id, path, event_type, observed_at, evidence)
                    VALUES (?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex, project.id, path, event_type, observed_at,
                        f"git status --porcelain=v1 reported {status_code!r}",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO file_activity_state (project_id, path, status_code, last_seen_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(project_id, path) DO UPDATE SET
                        status_code = excluded.status_code,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (project.id, path, status_code, observed_at),
                )
                events_created += 1

            for path in previous.keys() - snapshot.keys():
                connection.execute(
                    """
                    INSERT INTO file_events
                    (id, project_id, session_id, path, event_type, observed_at, evidence)
                    VALUES (?, ?, NULL, ?, 'clean', ?, 'Path no longer appears in Git working-tree status')
                    """,
                    (uuid.uuid4().hex, project.id, path, observed_at),
                )
                connection.execute(
                    "DELETE FROM file_activity_state WHERE project_id = ? AND path = ?",
                    (project.id, path),
                )
                events_created += 1

        return {
            "paths": len(snapshot),
            "events_created": events_created,
            "unchanged": len(snapshot) - sum(
                1 for path, (status, _) in snapshot.items() if previous.get(path) != status
            ),
        }

    def list_events(self, project: Project, limit: int = 30) -> list[dict[str, str]]:
        if not 1 <= limit <= 500:
            raise ValueError("Activity limit must be between 1 and 500.")
        with closing(connect(self.db_path)) as connection, connection:
            rows = connection.execute(
                """
                SELECT path, event_type, observed_at, evidence
                FROM file_events WHERE project_id = ?
                ORDER BY observed_at DESC, rowid DESC LIMIT ?
                """,
                (project.id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
