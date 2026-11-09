import subprocess
from pathlib import Path

from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    return path


def test_open_tasks_are_listed_across_projects(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    first = registry.register(_repo(tmp_path / "alpha"))
    second = registry.register(_repo(tmp_path / "beta"))
    store = JournalStore(db)
    store.add_task(first, "Write docs")
    done_id = store.add_task(second, "Ship it")
    store.add_task(second, "Fix picker")
    store.complete_task(second, done_id)

    assert store.count_open_tasks() == 2
    rows = store.recent_open_tasks(limit=5)
    assert {(row["project_name"], row["title"]) for row in rows} == {
        ("alpha", "Write docs"),
        ("beta", "Fix picker"),
    }
    assert len(store.recent_open_tasks(limit=1)) == 1
