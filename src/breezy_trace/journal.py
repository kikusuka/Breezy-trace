"""Project journal, task, and decision operations."""

import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from breezy_trace.config import database_path

from breezy_trace.database import connect
from breezy_trace.models import Project


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JournalStore:
    """Persist human-authored project context in the local SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or database_path()

    def _project(self, project: Project) -> None:
        with closing(connect(self.db_path)) as connection, connection:
            exists = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
        if not exists:
            raise ValueError("Project is not registered in this Breezy Trace database.")

    def add_note(self, project: Project, title: str, body: str = "") -> str:
        title = title.strip()
        if not title:
            raise ValueError("A journal entry needs a title.")
        self._project(project)
        entry_id, now = str(uuid.uuid4()), _now()
        with closing(connect(self.db_path)) as connection, connection:
            connection.execute(
                """INSERT INTO journal_entries
                   (id, project_id, title, body, entry_type, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'note', ?, ?)""",
                (entry_id, project.id, title, body, now, now),
            )
        return entry_id

    def list_entries(self, project: Project, limit: int = 20) -> list[sqlite3.Row]:
        self._project(project)
        if limit < 1:
            raise ValueError("Limit must be at least 1.")
        with closing(connect(self.db_path)) as connection, connection:
            return connection.execute(
                """SELECT id, title, body, entry_type, created_at, updated_at
                   FROM journal_entries WHERE project_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (project.id, limit),
            ).fetchall()

    def add_task(self, project: Project, title: str, details: str = "") -> str:
        title = title.strip()
        if not title:
            raise ValueError("A task needs a title.")
        self._project(project)
        task_id = str(uuid.uuid4())
        with closing(connect(self.db_path)) as connection, connection:
            connection.execute(
                """INSERT INTO project_tasks
                   (id, project_id, title, details, status, created_at)
                   VALUES (?, ?, ?, ?, 'open', ?)""",
                (task_id, project.id, title, details, _now()),
            )
        return task_id

    def list_tasks(self, project: Project, status: str | None = None) -> list[sqlite3.Row]:
        self._project(project)
        if status not in (None, "open", "done"):
            raise ValueError("Task status must be 'open', 'done', or omitted.")
        query = """SELECT id, title, details, status, created_at, completed_at
                   FROM project_tasks WHERE project_id = ?"""
        params: tuple[str, ...] = (project.id,)
        if status:
            query += " AND status = ?"
            params += (status,)
        query += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, created_at DESC"
        with closing(connect(self.db_path)) as connection, connection:
            return connection.execute(query, params).fetchall()

    def complete_task(self, project: Project, task_id: str) -> bool:
        self._project(project)
        with closing(connect(self.db_path)) as connection, connection:
            cursor = connection.execute(
                """UPDATE project_tasks SET status = 'done', completed_at = ?
                   WHERE id = ? AND project_id = ? AND status != 'done'""",
                (_now(), task_id, project.id),
            )
        return cursor.rowcount == 1

    def add_decision(
        self, project: Project, title: str, decision: str, context: str = ""
    ) -> str:
        title, decision = title.strip(), decision.strip()
        if not title or not decision:
            raise ValueError("A decision needs both a title and a decision.")
        self._project(project)
        decision_id = str(uuid.uuid4())
        with closing(connect(self.db_path)) as connection, connection:
            connection.execute(
                """INSERT INTO project_decisions
                   (id, project_id, title, context, decision, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (decision_id, project.id, title, context, decision, _now()),
            )
        return decision_id

    def list_decisions(self, project: Project, limit: int = 20) -> list[sqlite3.Row]:
        self._project(project)
        if limit < 1:
            raise ValueError("Limit must be at least 1.")
        with closing(connect(self.db_path)) as connection, connection:
            return connection.execute(
                """SELECT id, title, context, decision, created_at
                   FROM project_decisions WHERE project_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (project.id, limit),
            ).fetchall()
