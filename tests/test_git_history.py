import os
import subprocess
from datetime import date
from pathlib import Path

from breezy_trace.git import commit_activity, hot_files


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    )


def _commit(repo: Path, filename: str, text: str) -> None:
    (repo / filename).write_text(text, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", f"change {filename}")


def test_commit_activity_counts_commits_per_day(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _commit(repo, "a.txt", "1")
    _commit(repo, "a.txt", "2")
    assert commit_activity(repo, days=7) == {date.today(): 2}


def test_hot_files_ranks_most_changed_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _commit(repo, "a.txt", "1")
    _commit(repo, "a.txt", "2")
    _commit(repo, "b.txt", "1")
    assert hot_files(repo, days=7, limit=5) == [("a.txt", 2), ("b.txt", 1)]


def test_history_helpers_return_empty_outside_a_repository(tmp_path: Path) -> None:
    assert commit_activity(tmp_path / "missing") == {}
    assert hot_files(tmp_path / "missing") == []


def test_commit_graph_and_line_parsing(tmp_path: Path) -> None:
    from breezy_trace.git import commit_graph, parse_graph_line

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _commit(repo, "a.txt", "1")
    _commit(repo, "a.txt", "2")
    lines = commit_graph(repo, limit=10)
    assert len(lines) == 2 and all(line.startswith("*") for line in lines)
    graph, sha, refs, subject = parse_graph_line(lines[0])
    assert graph.strip() == "*" and len(sha) >= 7 and subject == "change a.txt"
    assert any(ref.startswith("HEAD") for ref in refs)
    assert commit_graph(tmp_path / "missing") == []

    assert parse_graph_line("| * 1a2b3c4 (origin/main, tag: v1) Fix thing") == (
        "| * ",
        "1a2b3c4",
        ["origin/main", "tag: v1"],
        "Fix thing",
    )
    assert parse_graph_line("|\\  ") == ("|\\  ", "", [], "")
