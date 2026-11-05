import json
import subprocess
from pathlib import Path

from breezy_trace.agents import AgentSessionStore, discover_claude_sessions, discover_opencode_sessions
from breezy_trace.registry import ProjectRegistry


def make_project(tmp_path: Path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    subprocess.run(["git", "init", str(project_path)], check=True, capture_output=True)
    project = ProjectRegistry(tmp_path / "trace.sqlite3").register(project_path)
    return project, tmp_path / "trace.sqlite3"


def test_claude_index_discovers_metadata_without_prompt_content(tmp_path: Path) -> None:
    project, _ = make_project(tmp_path)
    home = tmp_path / "claude"
    index_dir = home / "projects" / "project-key"
    index_dir.mkdir(parents=True)
    (index_dir / "sessions-index.json").write_text(json.dumps({
        "entries": [{
            "sessionId": "claude-session-1",
            "projectPath": project.path,
            "created": "2026-11-01T10:00:00Z",
            "modified": "2026-11-01T10:30:00Z",
            "gitBranch": "feature/test",
            "messageCount": 12,
            "firstPrompt": "PRIVATE PROMPT MUST NOT BE STORED",
            "summary": "PRIVATE SUMMARY MUST NOT BE STORED",
        }]
    }), encoding="utf-8")

    sessions = discover_claude_sessions(Path(project.path), home)

    assert len(sessions) == 1
    assert sessions[0].provider == "claude-code"
    assert sessions[0].metadata == {"git_branch": "feature/test", "message_count": 12}
    assert "PRIVATE" not in json.dumps(sessions[0].metadata)


def test_opencode_discovery_uses_session_metadata_only(tmp_path: Path) -> None:
    project, _ = make_project(tmp_path)
    root = tmp_path / "opencode" / "storage" / "session" / "project-id"
    root.mkdir(parents=True)
    (root / "session-1.json").write_text(json.dumps({
        "id": "opencode-session-1",
        "directory": project.path,
        "version": "1.2.3",
        "title": "PRIVATE TITLE NOT STORED",
        "time": {"created": 1793527200000, "updated": 1793529000000},
    }), encoding="utf-8")

    sessions = discover_opencode_sessions(Path(project.path), [tmp_path / "opencode" / "storage" / "session"])

    assert len(sessions) == 1
    assert sessions[0].provider == "opencode"
    assert sessions[0].metadata == {"version": "1.2.3"}


def test_session_sync_is_repeatable_and_project_scoped(tmp_path: Path, monkeypatch) -> None:
    project, db_path = make_project(tmp_path)
    other_path = tmp_path / "other"
    other_path.mkdir()
    subprocess.run(["git", "init", str(other_path)], check=True, capture_output=True)
    other = ProjectRegistry(db_path).register(other_path)

    claude = tmp_path / "claude"
    index_dir = claude / "projects" / "project-key"
    index_dir.mkdir(parents=True)
    (index_dir / "sessions-index.json").write_text(json.dumps({
        "entries": [{
            "sessionId": "session-repeat",
            "projectPath": project.path,
            "created": "2026-11-01T10:00:00Z",
            "modified": "2026-11-01T10:30:00Z",
            "messageCount": 4,
        }]
    }), encoding="utf-8")
    monkeypatch.setenv("BREEZY_TRACE_CLAUDE_HOME", str(claude))
    monkeypatch.setenv("BREEZY_TRACE_OPENCODE_HOME", str(tmp_path / "missing-opencode"))

    store = AgentSessionStore(db_path)
    assert store.sync(project) == 1
    assert store.sync(project) == 1
    assert len(store.list_sessions(project)) == 1
    assert store.list_sessions(other) == []
