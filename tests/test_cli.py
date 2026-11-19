import subprocess
import sys
from pathlib import Path

from breezy_trace import cli
from breezy_trace.registry import ProjectRegistry


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


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    return path


def _launch(monkeypatch, argv: list[str]) -> list[tuple[object, Path | None]]:
    calls: list[tuple[object, Path | None]] = []

    def record(args, project=None, unregistered_root=None):
        calls.append((project, unregistered_root))

    monkeypatch.setattr(cli, "_run_tui", record)
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    return calls


def _isolate_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BREEZY_TRACE_DATA_DIR", str(tmp_path / "data"))


def test_launch_in_unregistered_repository_opens_lobby_with_hint(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_data(monkeypatch, tmp_path)
    repo = _repo(tmp_path / "repo")
    monkeypatch.chdir(repo)

    def blocking_input(*_args, **_kwargs):
        raise AssertionError("blocking registration prompt was shown")

    monkeypatch.setattr("builtins.input", blocking_input)

    assert _launch(monkeypatch, ["breezy-trace"]) == [(None, repo.resolve())]


def test_launch_in_registered_project_opens_its_page(tmp_path: Path, monkeypatch) -> None:
    _isolate_data(monkeypatch, tmp_path)
    repo = _repo(tmp_path / "repo")
    project = ProjectRegistry().register(repo)
    monkeypatch.chdir(repo)

    assert _launch(monkeypatch, ["breezy-trace"]) == [(project, None)]


def test_home_command_opens_lobby_with_the_same_hint(tmp_path: Path, monkeypatch) -> None:
    _isolate_data(monkeypatch, tmp_path)
    repo = _repo(tmp_path / "repo")
    monkeypatch.chdir(repo)

    assert _launch(monkeypatch, ["breezy-trace", "home"]) == [(None, repo.resolve())]


def test_launch_never_opens_a_registered_home_repository(tmp_path: Path, monkeypatch) -> None:
    _isolate_data(monkeypatch, tmp_path)
    repo = _repo(tmp_path / "stray")
    ProjectRegistry().register(repo)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: repo))
    monkeypatch.chdir(repo)

    assert _launch(monkeypatch, ["breezy-trace"]) == [(None, None)]


def test_projects_marks_registered_home_folder(tmp_path: Path, monkeypatch, capsys) -> None:
    _isolate_data(monkeypatch, tmp_path)
    repo = _repo(tmp_path / "stray")
    ProjectRegistry().register(repo)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: repo))
    monkeypatch.setattr(sys, "argv", ["breezy-trace", "projects"])

    cli.main()

    assert "stray  (home folder, not a real project)" in capsys.readouterr().out
