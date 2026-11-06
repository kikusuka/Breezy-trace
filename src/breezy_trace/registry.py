"""Local project registration and lookup."""

import os
import sqlite3
import subprocess
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from breezy_trace.config import database_path
from breezy_trace.database import connect
from breezy_trace.models import Project


class ProjectError(ValueError):
    """Raised when a project cannot be registered or resolved."""


class ProjectRegistry:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or database_path()

    def _connect(self) -> sqlite3.Connection:
        return connect(self.db_path)

    @staticmethod
    def resolve_git_root(path: Path) -> Path:
        candidate = path.expanduser().resolve()
        if not candidate.exists():
            raise ProjectError(f"Path does not exist: {candidate}")
        try:
            # Ignore inherited repository overrides. A parent shell or IDE may
            # export GIT_DIR/GIT_WORK_TREE, making an unrelated folder appear
            # to belong to that repository.
            env = os.environ.copy()
            for key in (
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_COMMON_DIR",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            ):
                env.pop(key, None)
            result = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
                timeout=12,
                env=env,
            )
        except FileNotFoundError as error:
            raise ProjectError("Git is not installed or is not available on PATH.") from error
        except subprocess.TimeoutExpired as error:
            raise ProjectError("Git repository discovery timed out.") from error
        if result.returncode != 0:
            raise ProjectError(f"Not inside a Git repository: {candidate}")
        return Path(result.stdout.strip()).resolve()

    def register(self, path: Path, name: str | None = None) -> Project:
        root = self.resolve_git_root(path)
        now = datetime.now(UTC).isoformat()
        project = Project(
            id=str(uuid.uuid4()),
            name=(name or root.name).strip(),
            path=str(root),
            registered_at=now,
        )
        if not project.name:
            raise ProjectError("Project name cannot be empty.")
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """
                    INSERT INTO projects (id, name, path, registered_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (project.id, project.name, project.path, project.registered_at),
                )
        except sqlite3.IntegrityError as error:
            raise ProjectError(f"This project is already registered: {root}") from error
        return project

    def unregister(self, name_or_path: str) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM projects WHERE name = ? OR path = ?",
                (name_or_path, str(Path(name_or_path).expanduser().resolve())),
            )
            return cursor.rowcount > 0

    def list_projects(self) -> list[Project]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT id, name, path, registered_at, last_opened_at
                FROM projects ORDER BY COALESCE(last_opened_at, registered_at) DESC
                """
            ).fetchall()
        return [Project(**dict(row)) for row in rows]

    def find_by_path(self, path: Path) -> Project | None:
        try:
            root = self.resolve_git_root(path)
        except ProjectError:
            return None
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT id, name, path, registered_at, last_opened_at
                FROM projects WHERE path = ?
                """,
                (str(root),),
            ).fetchone()
        return Project(**dict(row)) if row else None

    def mark_opened(self, project_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE projects SET last_opened_at = ? WHERE id = ?",
                (now, project_id),
            )
