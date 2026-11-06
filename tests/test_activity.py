import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from breezy_trace.activity import FileActivityStore, _parse_porcelain
from breezy_trace.database import connect
from breezy_trace.registry import ProjectRegistry


def make_project(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Trace Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "trace@example.invalid"], check=True)
    db_path = tmp_path / "trace.sqlite3"
    project = ProjectRegistry(db_path).register(root)
    return root, project, db_path


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_scan_records_only_state_transitions_and_clean_transition(tmp_path: Path) -> None:
    root, project, db_path = make_project(tmp_path)
    file_path = root / "new file.txt"
    file_path.write_text("private contents are never read by the scanner", encoding="utf-8")
    store = FileActivityStore(db_path)

    first = store.scan(project)
    assert first["paths"] == 1
    assert first["events_created"] == 1
    assert store.scan(project)["events_created"] == 0
    assert store.list_events(project)[0]["event_type"] == "untracked"

    git(root, "add", "new file.txt")
    staged = store.scan(project)
    assert staged["events_created"] == 1
    assert store.list_events(project)[0]["event_type"] == "staged"

    git(root, "commit", "-m", "add file")
    clean = store.scan(project)
    assert clean["paths"] == 0
    assert clean["events_created"] == 1
    assert store.list_events(project)[0]["event_type"] == "clean"


def test_porcelain_parser_handles_spaces_newlines_and_rename_records() -> None:
    parsed = _parse_porcelain(
        b"?? file with spaces.txt\0"
        b"?? line\nbreak.txt\0"
        b"R  renamed target.txt\0old name.txt\0"
    )
    assert set(parsed) == {"file with spaces.txt", "line\nbreak.txt", "renamed target.txt"}
    assert parsed["renamed target.txt"] == ("R ", "renamed")


def test_scan_records_renames_without_reading_file_content(tmp_path: Path) -> None:
    root, project, db_path = make_project(tmp_path)
    original = root / "before.txt"
    original.write_text("content", encoding="utf-8")
    git(root, "add", "before.txt")
    git(root, "commit", "-m", "initial")
    git(root, "mv", "before.txt", "after.txt")

    summary = FileActivityStore(db_path).scan(project)

    assert summary["paths"] == 1
    event = FileActivityStore(db_path).list_events(project)[0]
    assert event["path"] == "after.txt"
    assert event["event_type"] == "renamed"


def test_activity_is_project_scoped_and_limit_is_validated(tmp_path: Path) -> None:
    root, project, db_path = make_project(tmp_path)
    other_root = tmp_path / "other"
    other_root.mkdir()
    git(other_root, "init")
    other = ProjectRegistry(db_path).register(other_root)
    (root / "one.txt").write_text("x", encoding="utf-8")

    store = FileActivityStore(db_path)
    store.scan(project)

    assert len(store.list_events(project)) == 1
    assert store.list_events(other) == []
    with pytest.raises(ValueError):
        store.list_events(project, 0)


def test_scan_rejects_unregistered_project(tmp_path: Path) -> None:
    _root, project, db_path = make_project(tmp_path)
    ProjectRegistry(db_path).unregister(project.path)
    with pytest.raises(ValueError, match="not registered"):
        FileActivityStore(db_path).scan(project)



def test_scan_prunes_activity_events_older_than_90_days(tmp_path: Path) -> None:
    _root, project, db_path = make_project(tmp_path)
    with closing(connect(db_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO file_events
            (id, project_id, session_id, path, event_type, observed_at, evidence)
            VALUES ('old-event', ?, NULL, 'old.txt', 'modified', '2000-01-01T00:00:00+00:00', 'test')
            """,
            (project.id,),
        )

    FileActivityStore(db_path).scan(project)

    with closing(connect(db_path)) as connection, connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM file_events WHERE id = 'old-event'"
        ).fetchone()[0]
    assert remaining == 0
