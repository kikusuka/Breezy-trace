import subprocess
from pathlib import Path

from breezy_trace.git import inspect_status, recent_commits


def test_git_status_reports_untracked_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")

    status = inspect_status(tmp_path)

    assert status.untracked == 1
    assert status.clean is False
    assert "untracked" in status.summary


def test_git_status_reads_branch_before_first_commit(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    expected_branch = subprocess.run(
        ["git", "-C", str(tmp_path), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    status = inspect_status(tmp_path)

    assert status.branch == expected_branch


def test_recent_commits_returns_local_history(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "trace@example.test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Trace Test"],
        check=True,
    )
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "hello.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "Initial project"],
        check=True,
        capture_output=True,
    )

    commits = recent_commits(tmp_path)

    assert len(commits) == 1
    assert commits[0]["subject"] == "Initial project"
    assert len(commits[0]["sha"]) == 7


def test_git_status_labels_detached_head(tmp_path: Path) -> None:
    import subprocess

    from breezy_trace.git import inspect_status

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Trace Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "trace@example.invalid"],
        check=True,
    )
    (tmp_path / "file.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "file.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "initial"],
        check=True, capture_output=True,
    )
    subprocess.run(["git", "-C", str(tmp_path), "checkout", "--detach"], check=True, capture_output=True)

    assert inspect_status(tmp_path).branch == "detached HEAD"


def test_git_status_handles_missing_git(monkeypatch, tmp_path: Path) -> None:
    import subprocess

    from breezy_trace.git import inspect_status

    def missing_git(*_args, **_kwargs):
        raise FileNotFoundError("git executable not found")

    monkeypatch.setattr(subprocess, "run", missing_git)
    status = inspect_status(tmp_path)
    assert status.clean is False
    assert "unavailable" in status.summary.lower() or "unavailable" in status.branch.lower()



def test_git_status_counts_newline_filename_as_one_path(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "line\\nbreak.txt").write_text("hello", encoding="utf-8")

    status = inspect_status(tmp_path)

    assert status.untracked == 1
    assert status.clean is False


def test_terminal_text_replaces_control_characters() -> None:
    from breezy_trace.git import _clean_terminal_text

    cleaned = _clean_terminal_text("safe\\x1b[31mred\\x07\\nnext")
    assert "\\x1b" not in cleaned
    assert "\\x07" not in cleaned
    assert "safe" in cleaned and "red" in cleaned
    assert "\\nnext" in cleaned
