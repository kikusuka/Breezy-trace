from pathlib import Path
import subprocess

from breezy_trace.git import inspect_status


def test_git_status_reports_untracked_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")

    status = inspect_status(tmp_path)

    assert status.untracked == 1
    assert status.clean is False
    assert "untracked" in status.summary
