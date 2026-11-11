import json
import subprocess
from pathlib import Path

from breezy_trace.agents import (
    AgentSessionStore,
    discover_claude_sessions,
    discover_opencode_sessions,
)
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
    (index_dir / "sessions-index.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "sessionId": "claude-session-1",
                        "projectPath": project.path,
                        "created": "2026-11-01T10:00:00Z",
                        "modified": "2026-11-01T10:30:00Z",
                        "gitBranch": "feature/test",
                        "messageCount": 12,
                        "firstPrompt": "PRIVATE PROMPT MUST NOT BE STORED",
                        "summary": "PRIVATE SUMMARY MUST NOT BE STORED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sessions = discover_claude_sessions(Path(project.path), home)

    assert len(sessions) == 1
    assert sessions[0].provider == "claude-code"
    assert sessions[0].metadata == {"git_branch": "feature/test", "message_count": 12}
    assert "PRIVATE" not in json.dumps(sessions[0].metadata)


def test_opencode_discovery_uses_session_metadata_only(tmp_path: Path) -> None:
    project, _ = make_project(tmp_path)
    root = tmp_path / "opencode" / "storage" / "session" / "project-id"
    root.mkdir(parents=True)
    (root / "session-1.json").write_text(
        json.dumps(
            {
                "id": "opencode-session-1",
                "directory": project.path,
                "version": "1.2.3",
                "title": "PRIVATE TITLE NOT STORED",
                "time": {"created": 1793527200000, "updated": 1793529000000},
            }
        ),
        encoding="utf-8",
    )

    sessions = discover_opencode_sessions(
        Path(project.path), [tmp_path / "opencode" / "storage" / "session"]
    )

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
    (index_dir / "sessions-index.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "sessionId": "session-repeat",
                        "projectPath": project.path,
                        "created": "2026-11-01T10:00:00Z",
                        "modified": "2026-11-01T10:30:00Z",
                        "messageCount": 4,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BREEZY_TRACE_CLAUDE_HOME", str(claude))
    monkeypatch.setenv("BREEZY_TRACE_OPENCODE_HOME", str(tmp_path / "missing-opencode"))

    store = AgentSessionStore(db_path)
    assert store.sync(project) == 1
    assert store.sync(project) == 1
    assert len(store.list_sessions(project)) == 1
    assert store.list_sessions(other) == []


def test_agent_metadata_rejects_oversized_json_and_invalid_timestamps(tmp_path: Path) -> None:
    from breezy_trace.agents import MAX_METADATA_BYTES, _iso, _read_json

    oversized = tmp_path / "oversized.json"
    oversized.write_text(" " * (MAX_METADATA_BYTES + 1), encoding="utf-8")
    assert _read_json(oversized) is None
    assert _iso(float("inf")) is None
    assert _iso(10**100) is None


def test_agent_metadata_path_limit_is_deterministic(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.agents as agents_module

    paths = [tmp_path / name for name in ("z.json", "a.json", "m.json")]
    monkeypatch.setattr(agents_module, "MAX_DISCOVERY_FILES", 2)

    first = agents_module._bounded_metadata_paths(iter(paths))
    second = agents_module._bounded_metadata_paths(iter(reversed(paths)))

    assert first == second == [tmp_path / "a.json", tmp_path / "m.json"]


def test_agent_metadata_reader_rejects_symlinks_and_deep_json(tmp_path: Path) -> None:
    from breezy_trace.agents import _read_json

    target = tmp_path / "target.json"
    target.write_text('{"safe": true}', encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pass
    else:
        assert _read_json(link) is None

    deeply_nested = tmp_path / "nested.json"
    deeply_nested.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")
    assert _read_json(deeply_nested) is None
