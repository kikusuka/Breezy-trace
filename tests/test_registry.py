import subprocess
from pathlib import Path

import pytest

from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectError, ProjectRegistry


def make_repo(path: Path) -> Path:
    path.mkdir(exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    return path


def test_register_and_list_project(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "sample")
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")

    project = registry.register(repo)

    assert project.name == "sample"
    assert project.path == str(repo.resolve())
    assert registry.list_projects() == [project]


def test_register_nested_path_resolves_git_root(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "sample")
    nested = repo / "src"
    nested.mkdir()
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")

    project = registry.register(nested)

    assert project.path == str(repo.resolve())


def test_duplicate_registration_is_rejected(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "sample")
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    registry.register(repo)

    with pytest.raises(ProjectError, match="already registered"):
        registry.register(repo)


def test_non_git_directory_is_rejected(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "plain"
    directory.mkdir()
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")

    def git_reports_non_repository(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )

    monkeypatch.setattr("breezy_trace.registry.subprocess.run", git_reports_non_repository)

    with pytest.raises(ProjectError, match="Not inside a Git repository"):
        registry.register(directory)


def test_unregister_removes_project(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "sample")
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    project = registry.register(repo)

    assert registry.unregister(project.name) is True
    assert registry.list_projects() == []


def test_unregister_cascades_project_journal_data(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "sample")
    db_path = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db_path)
    project = registry.register(repo)
    store = JournalStore(db_path)
    store.add_note(project, "Private context", "Should be removed with project.")
    store.add_task(project, "Finish cleanup")

    assert registry.unregister(project.name) is True
    with pytest.raises(ValueError, match="not registered"):
        store.list_entries(project)


def test_non_git_directory_ignores_inherited_git_dir(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "plain"
    directory.mkdir()
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "external" / ".git"))
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    observed = {}

    def git_reports_non_repository(command, **kwargs):
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            command,
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )

    monkeypatch.setattr("breezy_trace.registry.subprocess.run", git_reports_non_repository)

    with pytest.raises(ProjectError, match="Not inside a Git repository"):
        registry.register(directory)

    assert not any(key.upper().startswith("GIT_") for key in observed["env"])


def test_home_folder_cannot_be_registered(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "owner-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    repo = make_repo(home)
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")

    with pytest.raises(
        ProjectError,
        match="This is your home folder, not a project. Register the project folder inside it",
    ):
        registry.register(repo)

    assert registry.find_by_path(repo) is None
    assert registry.list_projects() == []


def test_registered_home_repository_cannot_capture_folders_below_it(
    tmp_path: Path, monkeypatch
) -> None:
    stray = make_repo(tmp_path / "stray")
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    project = registry.register(stray)
    nested = stray / "src"
    nested.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: stray))

    assert registry.find_by_path(stray) is None
    assert registry.find_by_path(nested) is None
    assert registry.list_projects() == [project]


def test_parent_of_home_cannot_be_registered(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "owner-home"
    home.mkdir()
    repo = make_repo(tmp_path)
    nested = home / "src"
    nested.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")

    with pytest.raises(ProjectError, match="parent of your home folder, not a project"):
        registry.register(repo)

    assert registry.find_by_path(repo) is None
    assert registry.find_by_path(nested) is None


def test_filesystem_root_cannot_be_registered(tmp_path: Path, monkeypatch) -> None:
    root = Path(Path.home().anchor)
    monkeypatch.setattr(
        ProjectRegistry,
        "resolve_git_root",
        classmethod(lambda cls, path: root),
    )
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")

    with pytest.raises(ProjectError, match="not a project. Register the project folder"):
        registry.register(root)

    assert registry.find_by_path(root) is None
