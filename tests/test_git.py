import subprocess
from pathlib import Path

from breezy_trace.git import inspect_status


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
