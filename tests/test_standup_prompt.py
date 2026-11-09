import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from breezy_trace import prompt, standup
from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry

ME = "me@example.com"


def _git(repo: Path, *args: str, author: str = ME) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "Someone", "GIT_AUTHOR_EMAIL": author,
           "GIT_COMMITTER_NAME": "Someone", "GIT_COMMITTER_EMAIL": author}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    _git(path, "config", "user.email", ME)
    (path / "a.txt").write_text("1", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "my first commit")
    (path / "b.txt").write_text("2", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "teammate commit", author="other@example.com")
    return path


def test_standup_collects_my_work_and_formats_markdown(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    project = registry.register(_repo(tmp_path / "proj"))
    store = JournalStore(db)
    store.add_note(project, "Parked the picker")
    store.add_decision(project, "Storage", "SQLite")
    done_id = store.add_task(project, "Wire dialog")
    store.complete_task(project, done_id)
    store.add_task(project, "Write docs")

    since = datetime.now(UTC) - timedelta(days=1)
    report = standup.collect_standup(db, registry.list_projects(), since)
    assert len(report) == 1 and report[0].name == "proj"
    entry = report[0]
    assert [subject for _sha, _day, subject in entry.commits] == ["my first commit"]
    assert entry.done == ["Wire dialog"] and entry.next_up == ["Write docs"]
    assert entry.notes == ["Parked the picker"] and entry.decisions == [("Storage", "SQLite")]

    everyone = standup.collect_standup(db, registry.list_projects(), since, mine_only=False)
    assert {subject for _s, _d, subject in everyone[0].commits} == {"my first commit", "teammate commit"}

    text = standup.format_standup(report, 1)
    for expected in ("# Standup: last 24 hours", "## proj", "**Done**", "my first commit",
                     "- [x] Wire dialog", "**Decided**", "- Storage: SQLite", "**Notes**",
                     "**Next**", "- [ ] Write docs"):
        assert expected in text
    assert "teammate commit" not in text

    future = datetime.now(UTC) + timedelta(days=1)
    quiet = standup.collect_standup(db, registry.list_projects(), future)
    assert quiet[0].next_up == ["Write docs"] and not quiet[0].has_activity
    assert "Nothing recorded in this window." in standup.format_standup(quiet, 3)
    assert standup.window_label(3) == "last 3 days"


def test_prompt_segment_reports_state_compactly(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    repo = _repo(tmp_path / "proj")
    assert prompt.prompt_segment(registry, repo) == ""  # not registered yet
    project = registry.register(repo)

    assert prompt.prompt_segment(registry, repo, ascii_only=True).split()[0] == "proj"
    assert prompt.prompt_segment(registry, repo, ascii_only=True).endswith("ok")
    (repo / "new.txt").write_text("x", encoding="utf-8")
    assert " *1" in prompt.prompt_segment(registry, repo, ascii_only=True)
    assert "±1" in prompt.prompt_segment(registry, repo, ascii_only=False)
    JournalStore(db).add_task(project, "do it")
    assert prompt.prompt_segment(registry, repo, ascii_only=True).endswith("t1")
    assert prompt.prompt_segment(registry, repo, ascii_only=False).endswith("○1")
    assert prompt.prompt_segment(registry, repo, fast=True) == "proj t1"
    assert prompt.prompt_segment(registry, tmp_path) == ""  # outside any repository


def test_shell_snippets_cover_every_supported_shell() -> None:
    assert set(prompt.SNIPPETS) == set(prompt.SHELLS)
    for shell, snippet in prompt.SNIPPETS.items():
        assert "breezy-trace prompt" in snippet, shell
    assert "function prompt" in prompt.SNIPPETS["powershell"]
    assert "PS1" in prompt.SNIPPETS["bash"] and "PROMPT_SUBST" in prompt.SNIPPETS["zsh"]


def test_cli_prompt_and_standup_work_without_the_terminal_ui(tmp_path: Path) -> None:
    data = tmp_path / "data"
    env = {**os.environ, "XDG_DATA_HOME": str(data), "LOCALAPPDATA": str(data), "APPDATA": str(data),
           "HOME": str(tmp_path)}
    repo = _repo(tmp_path / "proj")
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "breezy_trace", *args], check=False, cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=60)

    outside = run("prompt", cwd=tmp_path)
    assert outside.returncode == 0 and outside.stdout.strip() == ""
    assert run("register", ".", cwd=repo).returncode == 0
    inside = run("prompt", cwd=repo)
    assert inside.returncode == 0 and inside.stdout.split()[0] == "proj"
    assert run("prompt", "--fast", cwd=repo).stdout.strip() == "proj"
    init = run("prompt", "--init", "powershell", cwd=repo)
    assert "function prompt" in init.stdout
    report = run("standup", "--days", "2", cwd=repo)
    assert report.returncode == 0 and "# Standup: last 2 days" in report.stdout
    assert "my first commit" in report.stdout and "teammate commit" not in report.stdout
    assert "teammate commit" in run("standup", "--all-authors", cwd=repo).stdout
    heading = run("todos", cwd=repo)
    assert heading.returncode == 0 and "TODO/FIXME comment" in heading.stdout
