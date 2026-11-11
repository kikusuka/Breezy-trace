import subprocess
import sys


def test_module_entrypoint_reports_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "breezy_trace", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "breezy-trace 0.1.0"


def test_cli_help_lists_backup_and_inspect() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "breezy_trace", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "backup" in result.stdout
    assert "inspect" in result.stdout
    assert "restore" in result.stdout
    assert "sessions" in result.stdout
    assert "branches" in result.stdout
    assert "activity" in result.stdout
    assert "code" in result.stdout
