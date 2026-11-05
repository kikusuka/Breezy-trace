"""Tests for project journal persistence."""

import subprocess
from pathlib import Path

import pytest

from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry


def registered_project(tmp_path: Path):
    repo = tmp_path / "project"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    return ProjectRegistry(tmp_path / "trace.sqlite3").register(repo)


def test_notes_are_saved_and_scoped_to_project(tmp_path: Path) -> None:
    project = registered_project(tmp_path)
    store = JournalStore(tmp_path / "trace.sqlite3")

    store.add_note(project, "Release plan", "Finish tests before tagging.")
    entries = store.list_entries(project)

    assert len(entries) == 1
    assert entries[0]["title"] == "Release plan"
    assert entries[0]["body"] == "Finish tests before tagging."


def test_tasks_can_be_completed(tmp_path: Path) -> None:
    project = registered_project(tmp_path)
    store = JournalStore(tmp_path / "trace.sqlite3")
    task_id = store.add_task(project, "Write documentation")

    assert store.list_tasks(project, "open")[0]["id"] == task_id
    assert store.complete_task(project, task_id) is True
    assert store.complete_task(project, task_id) is False
    assert store.list_tasks(project, "done")[0]["status"] == "done"


def test_decisions_preserve_context(tmp_path: Path) -> None:
    project = registered_project(tmp_path)
    store = JournalStore(tmp_path / "trace.sqlite3")
    store.add_decision(project, "Storage", "Use SQLite", "Keep core local-first.")

    decision = store.list_decisions(project)[0]
    assert decision["decision"] == "Use SQLite"
    assert decision["context"] == "Keep core local-first."


def test_empty_titles_are_rejected(tmp_path: Path) -> None:
    project = registered_project(tmp_path)
    store = JournalStore(tmp_path / "trace.sqlite3")

    with pytest.raises(ValueError, match="title"):
        store.add_note(project, "   ")
