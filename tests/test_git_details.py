import subprocess
from pathlib import Path

from breezy_trace.git import inspect_details


def test_git_details_reports_staged_and_unstaged_changes(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "trace@example.test"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Trace Test"], check=True)
    file = tmp_path / "sample.txt"
    file.write_text("first\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "initial"], check=True, capture_output=True
    )
    file.write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.txt"], check=True)
    file.write_text("unstaged\n", encoding="utf-8")

    details = inspect_details(tmp_path)

    assert "sample.txt" in str(details["staged_diff"])
    assert "sample.txt" in str(details["unstaged_diff"])
    assert details["conflicts"] == 0
    assert details["stashes"] == 0
