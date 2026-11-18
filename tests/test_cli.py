import subprocess
import sys


def test_module_entrypoint_reports_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "breezy_trace", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "breezy-trace 0.2.0"


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
    assert "update" in result.stdout


def test_update_help_lists_check_and_yes() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "breezy_trace", "update", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--check" in result.stdout
    assert "--yes" in result.stdout
