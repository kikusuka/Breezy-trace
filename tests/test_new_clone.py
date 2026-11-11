import os
import subprocess
import sys
from pathlib import Path

from breezy_trace import actions
from breezy_trace.registry import ProjectError, ProjectRegistry


def _expect_error(call, fragment: str) -> None:
    try:
        call()
    except ProjectError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"expected ProjectError containing {fragment!r}")


def _git(*args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e.com",
    }
    subprocess.run(["git", *args], check=True, capture_output=True, text=True, env=env)


def test_create_project_makes_a_registered_repository(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    project = actions.create_project(registry, tmp_path, "my-new tool")
    assert (tmp_path / "my-new tool" / ".git").is_dir()
    assert project.name == "my-new tool" and [p.name for p in registry.list_projects()] == [
        "my-new tool"
    ]
    _expect_error(
        lambda: actions.create_project(registry, tmp_path, "my-new tool"), "already registered"
    )


def test_create_project_refuses_bad_names_and_non_empty_folders(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    for bad in ("", "../escape", "a/b", "a\\b", ".hidden", "name.", " "):
        _expect_error(
            lambda bad=bad: actions.create_project(registry, tmp_path, bad), "project name"
        )
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "file.txt").write_text("keep", encoding="utf-8")
    _expect_error(lambda: actions.create_project(registry, tmp_path, "busy"), "not empty")
    assert (busy / "file.txt").read_text(encoding="utf-8") == "keep" and not (
        busy / ".git"
    ).exists()
    _expect_error(
        lambda: actions.create_project(registry, tmp_path / "missing", "x"), "not a folder"
    )


def test_clone_project_clones_registers_and_validates_input(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git("init", "-q", str(source))
    (source / "a.txt").write_text("hello", encoding="utf-8")
    _git("-C", str(source), "add", ".")
    _git("-C", str(source), "commit", "-q", "-m", "init")
    bare = tmp_path / "remote" / "cool-repo.git"
    bare.parent.mkdir()
    _git("clone", "-q", "--bare", str(source), str(bare))

    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    workspace = tmp_path / "work"
    workspace.mkdir()
    project = actions.clone_project(registry, str(bare), workspace)
    assert project.name == "cool-repo" and (workspace / "cool-repo" / "a.txt").exists()
    assert [p.name for p in registry.list_projects()] == ["cool-repo"]
    _expect_error(lambda: actions.clone_project(registry, str(bare), workspace), "already exists")
    for bad in ("", "--upload-pack=evil", "two words", "-x"):
        _expect_error(
            lambda bad=bad: actions.clone_project(registry, bad, workspace), "repository URL"
        )
    _expect_error(
        lambda: actions.clone_project(registry, str(tmp_path / "nope.git"), workspace),
        "clone failed",
    )


def test_clone_names_and_credential_redaction() -> None:
    assert actions.clone_name("https://github.com/kiku/breezy-trace.git") == "breezy-trace"
    assert actions.clone_name("git@gitlab.com:group/sub/tool.git") == "tool"
    assert actions.clone_name("/srv/git/local.git") == "local"
    redacted = actions._redact("fatal: unable to access 'https://user:tok3n@github.com/o/r.git/'")
    assert "tok3n" not in redacted and "github.com/o/r.git" in redacted


def test_cli_new_and_clone_register_projects(tmp_path: Path) -> None:
    data = tmp_path / "data"
    env = {
        **os.environ,
        "BREEZY_TRACE_DATA_DIR": str(data),
        "XDG_DATA_HOME": str(data),
        "LOCALAPPDATA": str(data),
        "APPDATA": str(data),
        "HOME": str(tmp_path),
    }
    env["PYTHONPATH"] = (
        str(Path(__file__).resolve().parents[1] / "src") + os.pathsep + env.get("PYTHONPATH", "")
    )

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "breezy_trace", *args],
            check=False,
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    made = run("new", "fresh-idea")
    assert made.returncode == 0 and "Registered fresh-idea" in made.stdout
    assert (tmp_path / "fresh-idea" / ".git").is_dir()
    assert "fresh-idea" in run("projects").stdout
    failed = run("new", "../oops")
    assert failed.returncode == 1 and "project name" in failed.stderr
    bad = run("clone", "--upload-pack=evil")
    assert bad.returncode != 0
