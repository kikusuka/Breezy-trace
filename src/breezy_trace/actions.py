"""Manual actions shared by the terminal UI: the same operations the CLI exposes.

Each function does one explicit, local thing and returns a short human-readable result.
"""

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from breezy_trace.activity import FileActivityStore
from breezy_trace.agents import AgentSessionStore
from breezy_trace.backup import backup_database
from breezy_trace.code_index import PythonCodeIndex
from breezy_trace.git import hot_files, inspect_status, recent_commits
from breezy_trace.journal import JournalStore
from breezy_trace.metrics import find_todos
from breezy_trace.models import Project
from breezy_trace.polyglot_index import TreeSitterCodeIndex
from breezy_trace.registry import ProjectError, ProjectRegistry
from breezy_trace.remotes import parse_remote_url


def index_code(db_path: Path, project: Project) -> str:
    summary = PythonCodeIndex(db_path).index(project)
    parts = [
        (
            f"Python: {summary['files_indexed']} indexed, "
            f"{summary['files_unchanged']} unchanged, {summary['syntax_errors']} syntax errors"
        )
    ]
    if TreeSitterCodeIndex.available():
        other = TreeSitterCodeIndex(db_path).index(project)
        parts.append(
            f"Tree-sitter: {other['files_indexed']} indexed, {other['files_unchanged']} unchanged"
        )
    else:
        parts.append("other languages need: pip install 'breezy-trace[code]'")
    return " · ".join(parts)


def scan_activity(db_path: Path, project: Project) -> str:
    summary = FileActivityStore(db_path).scan(project)
    return (
        f"Scanned working tree: {summary['paths']} changed paths, "
        f"{summary['events_created']} new activity events."
    )


def sync_sessions(db_path: Path, project: Project) -> str:
    count = AgentSessionStore(db_path).sync(project)
    return f"Scanned local agent indexes; {count} session records inserted or refreshed."


def backup_now(db_path: Path, target_dir: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"breezy-trace-backup-{stamp}.sqlite3"
    backup_database(db_path, target)
    return target.resolve()


def _one_line(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def build_handoff(db_path: Path, project: Project) -> str:
    """Markdown summary of where a project stands, for a teammate or any coding agent.

    Built only from local Git state and what you recorded in the journal.
    """
    path = Path(project.path)
    status = inspect_status(path)
    store = JournalStore(db_path)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"# {project.name}: handoff",
        "",
        f"_Generated {stamp} by Breezy Trace from local data._",
        "",
        f"- Path: `{project.path}`",
        f"- Branch: `{status.branch}`",
        (
            f"- Working tree: {status.staged} staged, {status.modified} modified, "
            f"{status.untracked} untracked"
        ),
    ]
    if status.ahead or status.behind:
        out.append(f"- Upstream: {status.ahead} ahead, {status.behind} behind")

    out += ["", "## Latest notes"]
    notes = store.list_entries(project, limit=3)
    for note in notes:
        body = f": {_one_line(note['body'])}" if note["body"] else ""
        out.append(f"- **{_one_line(note['title'], 100)}** ({note['created_at'][:10]}){body}")
    if not notes:
        out.append("- None recorded.")

    out += ["", "## Open tasks"]
    tasks = store.list_tasks(project, "open")
    out += [f"- [ ] {_one_line(task['title'], 140)}" for task in tasks] or ["- None."]

    out += ["", "## Decisions"]
    decisions = store.list_decisions(project, limit=5)
    for decision in decisions:
        why = f" (why: {_one_line(decision['context'], 140)})" if decision["context"] else ""
        out.append(
            f"- **{_one_line(decision['title'], 100)}**: {_one_line(decision['decision'], 160)}{why}"
        )
    if not decisions:
        out.append("- None recorded.")

    out += ["", "## Recent commits"]
    commits = recent_commits(path, limit=8)
    out += [f"- `{c['sha']}` {c['date']} {_one_line(c['subject'], 120)}" for c in commits] or [
        "- No commits available."
    ]

    hot = hot_files(path, days=30, limit=6)
    if hot:
        out += ["", "## Most changed files (30 days)"]
        out += [f"- `{name}` ({count} commits)" for name, count in hot]
    return "\n".join(out) + "\n"


def export_handoff(db_path: Path, project: Project, target_dir: Path) -> Path:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project.name).strip("-") or "project"
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"handoff-{slug}-{stamp}.md"
    target.write_text(build_handoff(db_path, project), encoding="utf-8")
    return target.resolve()


def import_todos(db_path: Path, project: Project, limit: int = 50) -> str:
    """Turn TODO/FIXME comments into tasks. Re-running never duplicates a task, and no
    more than ``limit`` are created at once so a noisy codebase cannot flood the list."""
    store = JournalStore(db_path)
    existing = {row["title"] for row in store.list_tasks(project)}
    added = skipped = deferred = 0
    for name, line, text in find_todos(Path(project.path)):
        title = f"{text}  [{name}]"[:200]
        if title in existing:
            skipped += 1
        elif added >= limit:
            deferred += 1
        else:
            store.add_task(project, title, f"Imported from {name}:{line}")
            existing.add(title)
            added += 1
    message = f"Imported {added} task{'s' if added != 1 else ''} from TODO/FIXME comments"
    if skipped:
        message += f" ({skipped} already tracked)"
    if deferred:
        message += f"; {deferred} more waiting, run it again"
    return message + "."


_PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")


def _redact(text: str) -> str:
    """Remove credentials a user may have typed into a URL from any message we show."""
    return re.sub(r"(://)[^/\s@]+@", r"\1", text)


def _valid_parent(parent: Path) -> Path:
    parent = parent.expanduser()
    if not parent.is_dir():
        raise ProjectError(f"{parent} is not a folder that exists.")
    return parent


def create_project(registry: ProjectRegistry, parent: Path, name: str) -> Project:
    """Make a new folder with an empty Git repository and register it.

    This is the one place Trace writes to disk outside its own database, and only
    because you asked for a new project. It never touches an existing repository.
    """
    name = name.strip()
    if not _PROJECT_NAME.match(name) or name.endswith((".", " ")):
        raise ProjectError("Use letters, numbers, spaces, '.', '_' or '-' in the project name.")
    target = _valid_parent(parent) / name
    if target.exists() and any(target.iterdir()) and not (target / ".git").exists():
        raise ProjectError(f"{target} already exists and is not empty.")
    target.mkdir(exist_ok=True)
    if not (target / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "init", "-q", str(target)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ProjectError(f"Could not run git: {error}") from error
        if result.returncode != 0:
            raise ProjectError("git init failed: " + (result.stderr.strip() or "unknown error"))
    return registry.register(target)


def clone_name(url: str) -> str:
    remote = parse_remote_url("origin", url)
    base = remote.slug.rsplit("/", 1)[-1] if remote else Path(url.rstrip("/\\")).name
    return base.removesuffix(".git")


def clone_project(registry: ProjectRegistry, url: str, parent: Path) -> Project:
    """``git clone`` a remote (GitHub, GitLab, ...) into ``parent`` and register it.

    Uses the network only because you asked. Credentials stay with Git; Trace never
    stores or shows them, and Git is told not to prompt (the terminal UI owns the screen).
    """
    url = url.strip()
    if not url or url.startswith("-") or any(char.isspace() for char in url):
        raise ProjectError("That does not look like a repository URL.")
    name = clone_name(url)
    if not _PROJECT_NAME.match(name):
        raise ProjectError("Could not work out a folder name from that URL.")
    target = _valid_parent(parent) / name
    if target.exists():
        raise ProjectError(f"{target} already exists.")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        result = subprocess.run(
            ["git", "clone", "--", url, str(target)],
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        raise ProjectError("git clone took too long and was stopped.") from error
    except OSError as error:
        raise ProjectError(f"Could not run git: {error}") from error
    if result.returncode != 0:
        lines = [line for line in result.stderr.strip().splitlines() if line.strip()]
        raise ProjectError("git clone failed: " + _redact(lines[-1] if lines else "unknown error"))
    return registry.register(target)


def clean_path_text(text: str) -> str:
    """Tidy a path typed or pasted (or dropped from Explorer): trim spaces and the quotes
    Windows adds around paths that contain spaces."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def adopt_folder(registry: ProjectRegistry, folder: Path) -> Project:
    """Register ``folder``, first creating an empty Git repository if it has none."""
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise ProjectError(f"{folder} is not a folder.")
    if not (folder / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "init", "-q", str(folder)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ProjectError(f"Could not run git: {error}") from error
        if result.returncode != 0:
            raise ProjectError("git init failed: " + (result.stderr.strip() or "unknown error"))
    return registry.register(folder)


def resolve_open_target(registry: ProjectRegistry, target: Path, confirm_init) -> Project:
    """The project for ``target`` (a folder from Explorer or the shell): reuse it when
    registered, register it when it is a Git repository, and for a plain folder ask
    ``confirm_init(message)`` before creating a repository there."""
    target = Path(clean_path_text(str(target))).expanduser().resolve()
    existing = registry.find_by_path(target)
    if existing is not None:
        return existing
    try:
        return registry.register(target)
    except ProjectError as error:
        if not target.is_dir() or not str(error).startswith("Not inside a Git repository"):
            raise
        message = (
            f"{target} is not a Git repository.\n"
            "Create an empty Git repository here and add it to Breezy Trace?"
        )
        if not confirm_init(message):
            raise ProjectError("Cancelled; nothing was changed.") from error
        return adopt_folder(registry, target)
