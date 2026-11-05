import subprocess
from pathlib import Path

import pytest

from breezy_trace.registry import ProjectError, ProjectRegistry


def make_repo(path: Path) -> Path:
    path.mkdir()
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


def test_non_git_directory_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "plain"
    directory.mkdir()
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")

    with pytest.raises(ProjectError, match="Not inside a Git repository"):
        registry.register(directory)


def test_unregister_removes_project(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "sample")
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    project = registry.register(repo)

    assert registry.unregister(project.name) is True
    assert registry.list_projects() == []
