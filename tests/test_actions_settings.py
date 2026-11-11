import subprocess
from pathlib import Path

from breezy_trace import actions, settings
from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    (path / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@e.com",
            "commit",
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def test_manual_actions_return_readable_results(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    project = registry.register(_repo(tmp_path / "proj"))
    (tmp_path / "proj" / "scratch.txt").write_text("x", encoding="utf-8")

    assert "Python: 1 indexed" in actions.index_code(db, project)
    assert "1 changed paths" in actions.scan_activity(db, project)
    assert "session records" in actions.sync_sessions(db, project)
    backup = actions.backup_now(db, tmp_path / "backups")
    assert backup.exists() and backup.name.startswith("breezy-trace-backup-")


def test_journal_totals_count_everything_across_projects(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    one = registry.register(_repo(tmp_path / "one"))
    two = registry.register(_repo(tmp_path / "two"))
    store = JournalStore(db)
    store.add_note(one, "n1")
    store.add_note(two, "n2")
    task = store.add_task(one, "t1")
    store.add_task(two, "t2")
    store.complete_task(one, task)
    store.add_decision(two, "d", "yes")
    assert store.totals() == {"notes": 2, "open_tasks": 1, "done_tasks": 1, "decisions": 1}


def test_settings_round_trip_and_ignore_corruption(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "settings_path", lambda: tmp_path / "settings.json")
    assert settings.load_settings() == {}
    settings.save_setting("theme", "midnight")
    assert settings.load_settings() == {"theme": "midnight"}
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    assert settings.load_settings() == {}


def test_search_finds_notes_tasks_and_decisions_and_escapes_wildcards(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    one = registry.register(_repo(tmp_path / "alpha"))
    two = registry.register(_repo(tmp_path / "beta"))
    store = JournalStore(db)
    store.add_note(one, "Picker redesign", "wide layout for the PICKER")
    store.add_task(two, "Fix picker bug", "")
    store.add_decision(two, "Storage", "Use SQLite", "picker needs fast lookups")
    store.add_note(two, "100% done", "")

    rows = store.search_all("picker")
    assert {(row["project_name"], row["kind"]) for row in rows} == {
        ("alpha", "note"),
        ("beta", "task"),
        ("beta", "decision"),
    }
    assert store.search_all("zzz") == []
    assert store.search_all("   ") == []
    assert [row["title"] for row in store.search_all("100%")] == ["100% done"]
    assert store.search_all("%") != [] and len(store.search_all("%")) == 1  # literal percent only
    assert len(store.search_all("picker", limit=2)) == 2


def test_handoff_summarises_state_and_exports_markdown(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    project = registry.register(_repo(tmp_path / "proj"))
    store = JournalStore(db)
    store.add_note(project, "Resume here", "pick up the picker work")
    store.add_task(project, "Wire the picker")
    store.add_decision(project, "Storage", "Use SQLite", "simple and local")

    text = actions.build_handoff(db, project)
    for expected in (
        "# proj: handoff",
        "## Latest notes",
        "**Resume here**",
        "- [ ] Wire the picker",
        "**Storage**: Use SQLite (why: simple and local)",
        "## Recent commits",
        "`app.py`",
    ):
        assert expected in text
    exported = actions.export_handoff(db, project, tmp_path / "handoffs")
    assert exported.exists() and exported.name.startswith("handoff-proj-")
    assert exported.read_text(encoding="utf-8") == text or "Generated" in exported.read_text(
        encoding="utf-8"
    )
