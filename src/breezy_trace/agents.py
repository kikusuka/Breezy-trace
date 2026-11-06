"""Metadata-only discovery for supported coding-agent session stores.

Transcript files are deliberately never opened. Only provider session indexes and
session metadata documents are inspected.
"""

import hashlib
import json
import os
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from heapq import nsmallest
from pathlib import Path

from breezy_trace.database import connect
from breezy_trace.models import Project

MAX_METADATA_BYTES = 5_000_000
MAX_DISCOVERY_FILES = 2_000


@dataclass(frozen=True, slots=True)
class AgentSession:
    provider: str
    external_id: str
    started_at: str | None
    ended_at: str | None
    source: str
    metadata: dict[str, object]


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            if not isinstance(value, bool):
                timestamp = value / 1000 if value > 10_000_000_000 else value
                return datetime.fromtimestamp(timestamp, UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        return value
    return None


def _read_json(path: Path) -> dict[str, object] | None:
    """Read a bounded metadata document without trusting a prior size check."""
    try:
        if path.is_symlink():
            return None
        with path.open("rb") as stream:
            raw = stream.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _bounded_metadata_paths(paths) -> list[Path]:
    """Select a deterministic, memory-bounded subset of metadata paths."""
    return nsmallest(MAX_DISCOVERY_FILES, paths, key=lambda path: path.as_posix())


def _project_matches(value: object, project_path: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return Path(value).expanduser().resolve() == project_path
    except (OSError, RuntimeError):
        return False


def _claude_home() -> Path:
    override = os.environ.get("BREEZY_TRACE_CLAUDE_HOME")
    return Path(override).expanduser() if override else Path.home() / ".claude"


def _opencode_roots() -> list[Path]:
    override = os.environ.get("BREEZY_TRACE_OPENCODE_HOME")
    if override:
        return [Path(override).expanduser() / "storage" / "session"]
    home = Path.home()
    candidates = [
        home / ".local" / "share" / "opencode" / "storage" / "session",
        home / "Library" / "Application Support" / "opencode" / "storage" / "session",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "opencode" / "storage" / "session")
    return candidates


def discover_claude_sessions(project_path: Path, claude_home: Path | None = None) -> list[AgentSession]:
    """Read only Claude Code sessions-index.json metadata for this project."""
    root = (claude_home or _claude_home()) / "projects"
    project_path = project_path.expanduser().resolve()
    if not root.is_dir():
        return []
    found: list[AgentSession] = []
    for index_path in _bounded_metadata_paths(root.glob("*/sessions-index.json")):
        index = _read_json(index_path)
        if not index:
            continue
        entries = index.get("entries", [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not _project_matches(entry.get("projectPath"), project_path):
                continue
            external_id = entry.get("sessionId")
            if not isinstance(external_id, str) or not external_id:
                continue
            safe_metadata: dict[str, object] = {}
            branch = entry.get("gitBranch")
            count = entry.get("messageCount")
            if isinstance(branch, str):
                safe_metadata["git_branch"] = branch
            if isinstance(count, int) and count >= 0:
                safe_metadata["message_count"] = count
            found.append(AgentSession(
                provider="claude-code",
                external_id=external_id,
                started_at=_iso(entry.get("created")),
                ended_at=_iso(entry.get("modified")),
                source="sessions-index",
                metadata=safe_metadata,
            ))
    return found


def discover_opencode_sessions(
    project_path: Path, roots: list[Path] | None = None
) -> list[AgentSession]:
    """Read OpenCode session JSON metadata; never inspect message storage."""
    project_path = project_path.expanduser().resolve()
    found: list[AgentSession] = []
    for root in roots if roots is not None else _opencode_roots():
        if not root.is_dir():
            continue
        for session_path in _bounded_metadata_paths(root.glob("*/*.json")):
            session = _read_json(session_path)
            if not session or not _project_matches(session.get("directory"), project_path):
                continue
            external_id = session.get("id")
            if not isinstance(external_id, str) or not external_id:
                continue
            times = session.get("time")
            times = times if isinstance(times, dict) else {}
            safe_metadata: dict[str, object] = {}
            version = session.get("version")
            if isinstance(version, str):
                safe_metadata["version"] = version
            found.append(AgentSession(
                provider="opencode",
                external_id=external_id,
                started_at=_iso(times.get("created")),
                ended_at=_iso(times.get("updated")),
                source="session-metadata",
                metadata=safe_metadata,
            ))
    return found


class AgentSessionStore:
    """Persist and list metadata-only agent sessions for registered projects."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def sync(self, project: Project) -> int:
        sessions = discover_claude_sessions(Path(project.path))
        sessions.extend(discover_opencode_sessions(Path(project.path)))
        with closing(connect(self.db_path)) as connection, connection:
            exists = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
            if not exists:
                raise ValueError("Project is not registered in this Breezy Trace database.")
            inserted = 0
            for session in sessions:
                stable_id = hashlib.sha256(
                    f"{project.id}:{session.provider}:{session.external_id}".encode()
                ).hexdigest()
                cursor = connection.execute(
                    """
                    INSERT INTO agent_sessions
                    (id, project_id, provider, external_id, started_at, ended_at, source, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        started_at = excluded.started_at,
                        ended_at = excluded.ended_at,
                        source = excluded.source,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        stable_id, project.id, session.provider, session.external_id,
                        session.started_at, session.ended_at, session.source,
                        json.dumps(session.metadata, sort_keys=True),
                    ),
                )
                inserted += cursor.rowcount
            return inserted

    def list_sessions(self, project: Project, limit: int = 20) -> list[dict[str, object]]:
        if limit < 1:
            raise ValueError("Limit must be positive.")
        with closing(connect(self.db_path)) as connection, connection:
            rows = connection.execute(
                """
                SELECT provider, external_id, started_at, ended_at, source, metadata_json
                FROM agent_sessions WHERE project_id = ?
                ORDER BY COALESCE(ended_at, started_at) DESC LIMIT ?
                """,
                (project.id, limit),
            ).fetchall()
        return [
            {
                "provider": row["provider"],
                "external_id": row["external_id"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "source": row["source"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]
