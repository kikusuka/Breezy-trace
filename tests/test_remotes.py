import subprocess
from pathlib import Path

from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry
from breezy_trace.remotes import list_remotes, parse_remote_url, primary_remote, provider_for


def test_common_remote_url_shapes_are_parsed() -> None:
    cases = [
        (
            "git@github.com:kiku/breezy-trace.git",
            "GitHub",
            "kiku/breezy-trace",
            "https://github.com/kiku/breezy-trace",
        ),
        (
            "https://github.com/kiku/breezy-trace",
            "GitHub",
            "kiku/breezy-trace",
            "https://github.com/kiku/breezy-trace",
        ),
        (
            "https://gitlab.com/group/sub/repo.git",
            "GitLab",
            "group/sub/repo",
            "https://gitlab.com/group/sub/repo",
        ),
        (
            "ssh://git@bitbucket.org/team/repo.git",
            "Bitbucket",
            "team/repo",
            "https://bitbucket.org/team/repo",
        ),
        ("https://codeberg.org/u/r", "Codeberg", "u/r", "https://codeberg.org/u/r"),
        ("https://gitlab.example.com/a/b.git", "GitLab", "a/b", "https://gitlab.example.com/a/b"),
        (
            "ssh://git@github.example.org:2222/o/r.git",
            "GitHub",
            "o/r",
            "https://github.example.org/o/r",
        ),
        ("https://git.example.org/u/r.git", "Git", "u/r", "https://git.example.org/u/r"),
    ]
    for raw, provider, slug, web in cases:
        remote = parse_remote_url("origin", raw)
        assert remote is not None, raw
        assert (remote.provider, remote.slug, remote.web_url) == (provider, slug, web), raw
    assert provider_for("GitHub.com") == "GitHub"


def test_credentials_in_urls_are_never_kept() -> None:
    remote = parse_remote_url("origin", "https://ghp_SECRETTOKEN123:x-oauth@github.com/kiku/r.git")
    assert remote is not None
    assert "SECRET" not in repr(remote) and "SECRET" not in remote.web_url
    assert remote.label == "GitHub · kiku/r"


def test_local_paths_and_garbage_are_not_remotes() -> None:
    for raw in (
        "/srv/git/x.git",
        "C:\\repos\\x",
        "C:/repos/x",
        "../x",
        "./x",
        "file:///srv/x.git",
        "",
        "   ",
        "~/code/x",
        "justaword",
    ):
        assert parse_remote_url("origin", raw) is None, raw


def test_list_remotes_reads_git_config_with_origin_first(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
    assert list_remotes(repo) == [] and primary_remote([]) is None
    for name, url in (
        ("backup", "https://gitlab.com/me/backup.git"),
        ("origin", "git@github.com:me/main.git"),
        ("local", "/srv/git/local.git"),
    ):
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", name, url],
            check=True,
            capture_output=True,
            text=True,
        )
    remotes = list_remotes(repo)
    assert [remote.name for remote in remotes] == ["origin", "backup"]  # local path ignored
    assert primary_remote(remotes).label == "GitHub · me/main"
    assert list_remotes(tmp_path / "missing") == []


def test_project_counts_describe_what_removal_deletes(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
    registry = ProjectRegistry(db)
    project = registry.register(repo)
    store = JournalStore(db)
    store.add_note(project, "n")
    first = store.add_task(project, "a")
    store.add_task(project, "b")
    store.complete_task(project, first)
    store.add_decision(project, "d", "yes")
    assert store.project_counts(project) == {
        "notes": 1,
        "open_tasks": 1,
        "done_tasks": 1,
        "decisions": 1,
    }
    assert registry.unregister(str(project.path)) is True
    assert store.totals() == {"notes": 0, "open_tasks": 0, "done_tasks": 0, "decisions": 0}
    assert (repo / ".git").exists()  # removing from Trace never touches the repository
