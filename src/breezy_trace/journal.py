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

    def recent_open_tasks(self, limit: int = 6) -> list[sqlite3.Row]:
        """Newest open tasks across every registered project (for the lobby)."""
        with closing(connect(self.db_path)) as connection, connection:
            return connection.execute(
                """SELECT t.title, t.created_at, p.name AS project_name
                   FROM project_tasks t JOIN projects p ON p.id = t.project_id
                   WHERE t.status = 'open'
                   ORDER BY t.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()

    def count_open_tasks(self) -> int:
        with closing(connect(self.db_path)) as connection, connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM project_tasks WHERE status = 'open'"
            ).fetchone()
        return int(row["count"])

    def totals(self) -> dict[str, int]:
        """Counts across every registered project, for the lobby."""
        with closing(connect(self.db_path)) as connection, connection:
            def count(sql: str) -> int:
                return int(connection.execute(sql).fetchone()[0])

            return {
                "notes": count("SELECT COUNT(*) FROM journal_entries"),
                "open_tasks": count("SELECT COUNT(*) FROM project_tasks WHERE status = 'open'"),
                "done_tasks": count("SELECT COUNT(*) FROM project_tasks WHERE status = 'done'"),
                "decisions": count("SELECT COUNT(*) FROM project_decisions"),
            }

    def search_all(self, query: str, limit: int = 40) -> list[sqlite3.Row]:
        """Case-insensitive text search over notes, tasks and decisions in every project."""
        query = query.strip()
        if not query:
            return []
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        with closing(connect(self.db_path)) as connection, connection:
            return connection.execute(
                r"""
                SELECT 'note' AS kind, e.title AS title, e.body AS detail,
                       e.created_at AS created_at, p.name AS project_name, '' AS status
                  FROM journal_entries e JOIN projects p ON p.id = e.project_id
                 WHERE e.title LIKE ?1 ESCAPE '\' OR e.body LIKE ?1 ESCAPE '\'
                UNION ALL
                SELECT 'task', t.title, t.details, t.created_at, p.name, t.status
                  FROM project_tasks t JOIN projects p ON p.id = t.project_id
                 WHERE t.title LIKE ?1 ESCAPE '\' OR t.details LIKE ?1 ESCAPE '\'
                UNION ALL
                SELECT 'decision', d.title,
                       d.decision || CASE WHEN d.context <> '' THEN ' - ' || d.context ELSE '' END,
                       d.created_at, p.name, ''
                  FROM project_decisions d JOIN projects p ON p.id = d.project_id
                 WHERE d.title LIKE ?1 ESCAPE '\' OR d.decision LIKE ?1 ESCAPE '\'
                    OR d.context LIKE ?1 ESCAPE '\'
                ORDER BY created_at DESC LIMIT ?2
                """,
                (pattern, limit),
            ).fetchall()

    def activity_since(self, project: Project, since: str) -> dict[str, list[sqlite3.Row]]:
        """Notes, decisions and completed tasks recorded for ``project`` since the ISO time."""
        with closing(connect(self.db_path)) as connection, connection:
            return {
                "notes": connection.execute(
                    "SELECT title, created_at FROM journal_entries "
                    "WHERE project_id = ? AND created_at >= ? ORDER BY created_at",
                    (project.id, since),
                ).fetchall(),
                "decisions": connection.execute(
                    "SELECT title, decision, created_at FROM project_decisions "
                    "WHERE project_id = ? AND created_at >= ? ORDER BY created_at",
                    (project.id, since),
                ).fetchall(),
                "done": connection.execute(
                    "SELECT title, completed_at FROM project_tasks "
                    "WHERE project_id = ? AND status = 'done' AND completed_at >= ? "
                    "ORDER BY completed_at",
                    (project.id, since),
                ).fetchall(),
            }

    def project_counts(self, project: Project) -> dict[str, int]:
        """What removing ``project`` from Trace would delete from the database."""
        with closing(connect(self.db_path)) as connection, connection:
            def count(sql: str) -> int:
                return int(connection.execute(sql, (project.id,)).fetchone()[0])

            return {
                "notes": count("SELECT COUNT(*) FROM journal_entries WHERE project_id = ?"),
                "open_tasks": count(
                    "SELECT COUNT(*) FROM project_tasks WHERE project_id = ? AND status = 'open'"
                ),
                "done_tasks": count(
                    "SELECT COUNT(*) FROM project_tasks WHERE project_id = ? AND status = 'done'"
                ),
                "decisions": count("SELECT COUNT(*) FROM project_decisions WHERE project_id = ?"),
            }

