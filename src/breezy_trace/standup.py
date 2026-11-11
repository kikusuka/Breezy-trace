"""Standup report: what you committed, finished and decided, plus what is next.

Built only from local Git history and the journal. Commits are limited to your own
(``git config user.email``) unless asked otherwise.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from breezy_trace.git import run_git
from breezy_trace.journal import JournalStore
from breezy_trace.models import Project

MAX_COMMITS = 40
MAX_NEXT = 5


@dataclass
class ProjectStandup:
    name: str
    commits: list[tuple[str, str, str]] = field(default_factory=list)  # sha, date, subject
    done: list[str] = field(default_factory=list)
    next_up: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    decisions: list[tuple[str, str]] = field(default_factory=list)  # title, decision

    @property
    def has_activity(self) -> bool:
        return bool(self.commits or self.done or self.notes or self.decisions)


def _my_email(path: Path) -> str:
    command = run_git(path, "config", "user.email")
    return command.stdout.strip() if command is not None and command.returncode == 0 else ""


def commits_since(
    path: Path, since: datetime, mine_only: bool = True
) -> list[tuple[str, str, str]]:
    stamp = since.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S +0000")
    args = [
        "log",
        "--branches",
        "--remotes",
        f"--since={stamp}",
        "--no-merges",
        "-n",
        str(MAX_COMMITS),
        "--format=%h%x09%as%x09%s",
    ]
    email = _my_email(path) if mine_only else ""
    if email:
        args += ["--fixed-strings", f"--author={email}"]
    command = run_git(path, *args, timeout=8)
    if command is None or command.returncode != 0:
        return []
    rows = [line.split("\t", 2) for line in command.stdout.splitlines() if line.count("\t") >= 2]
    return [(sha, day, subject) for sha, day, subject in rows]


def collect_standup(
    db_path: Path, projects: list[Project], since: datetime, mine_only: bool = True
) -> list[ProjectStandup]:
    """One entry per project that has activity in the window or work waiting."""
    store = JournalStore(db_path)
    stamp = since.astimezone(UTC).isoformat()
    report: list[ProjectStandup] = []
    for project in projects:
        recorded = store.activity_since(project, stamp)
        entry = ProjectStandup(
            name=project.name,
            commits=commits_since(Path(project.path), since, mine_only),
            done=[row["title"] for row in recorded["done"]],
            next_up=[row["title"] for row in store.list_tasks(project, "open")[:MAX_NEXT]],
            notes=[row["title"] for row in recorded["notes"]],
            decisions=[(row["title"], row["decision"]) for row in recorded["decisions"]],
        )
        if entry.has_activity or entry.next_up:
            report.append(entry)
    return report


def window_label(days: int) -> str:
    return "last 24 hours" if days == 1 else f"last {days} days"


def format_standup(report: list[ProjectStandup], days: int) -> str:
    """Markdown you can paste into chat or a standup doc."""
    out = [f"# Standup: {window_label(days)}", ""]
    if not any(entry.has_activity for entry in report):
        out += ["Nothing recorded in this window.", ""]
    for entry in report:
        out += [f"## {entry.name}"]
        if entry.commits or entry.done:
            out += ["", "**Done**"]
            out += [f"- `{sha}` {subject}" for sha, _day, subject in entry.commits]
            out += [f"- [x] {title}" for title in entry.done]
        if entry.decisions:
            out += ["", "**Decided**"]
            out += [f"- {title}: {decision}" for title, decision in entry.decisions]
        if entry.notes:
            out += ["", "**Notes**"]
            out += [f"- {title}" for title in entry.notes]
        if entry.next_up:
            out += ["", "**Next**"]
            out += [f"- [ ] {title}" for title in entry.next_up]
        out.append("")
    return "\n".join(out).rstrip() + "\n"
