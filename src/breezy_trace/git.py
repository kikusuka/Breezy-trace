"""Read-only Git inspection helpers with bounded subprocess execution."""

import re
import subprocess
import time
from collections import Counter
from datetime import date
from pathlib import Path

from breezy_trace.models import GitStatus

GIT_TIMEOUT_SECONDS = 5


def _clean_terminal_text(value: str) -> str:
    """Replace terminal control characters while preserving line/tab layout."""
    return re.sub(r"[\x01-\x08\x0b-\x1e\x7f-\x9f]", "�", value)


def _run(
    path: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str] | None:
    """Run a read-only Git command and return None when Git is unavailable or slow."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    # Git metadata can contain terminal control characters (for example in
    # commit subjects). Strip them before any caller renders the text.
    result.stdout = _clean_terminal_text(result.stdout)
    result.stderr = _clean_terminal_text(result.stderr)
    return result


def run_git(
    path: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str] | None:
    """Public wrapper for the read-only Git runner (used by the metrics module)."""
    return _run(path, *args, timeout=timeout)


def inspect_status(path: Path) -> GitStatus:
    """Read a concise Git status without changing repository state."""
    command = _run(path, "status", "--porcelain=v1", "--branch", "--ahead-behind", "-z")
    if command is None:
        return GitStatus.unavailable("Git is unavailable or the status command timed out.")
    if command.returncode != 0:
        reason = command.stderr.strip() or "Git status is unavailable."
        return GitStatus.unavailable(reason)

    # Porcelain -z uses NUL-delimited path records, so filenames containing
    # newlines cannot be mistaken for additional changed files.
    records = command.stdout.split("\0")
    branch_line = records[0] if records else "## unknown"
    branch_info = branch_line.removeprefix("## ")
    if branch_info.startswith("No commits yet on "):
        branch = _clean_terminal_text(branch_info.removeprefix("No commits yet on ").strip())
    elif branch_info.startswith("HEAD (no branch)"):
        branch = "detached HEAD"
    else:
        branch = _clean_terminal_text(branch_info.split("...", 1)[0].split(" ", 1)[0])

    ahead = behind = staged = modified = untracked = 0
    if "[" in branch_line and "]" in branch_line:
        tracking = branch_line.split("[", 1)[1].split("]", 1)[0]
        for part in tracking.split(","):
            part = part.strip()
            try:
                if part.startswith("ahead "):
                    ahead = int(part.removeprefix("ahead "))
                elif part.startswith("behind "):
                    behind = int(part.removeprefix("behind "))
            except ValueError:
                continue

    index = 1
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 3:
            continue
        code = record[:2]
        if code == "??":
            untracked += 1
        else:
            if code[0] not in {" ", "?"}:
                staged += 1
            if code[1] not in {" ", "?"}:
                modified += 1
        if "R" in code or "C" in code:
            # In -z mode rename/copy records are followed by the source path.
            index += 1

    total = staged + modified + untracked
    summary = (
        "Working tree clean"
        if total == 0
        else (f"{staged} staged · {modified} modified · {untracked} untracked")
    )
    return GitStatus(
        branch=branch or "unknown",
        staged=staged,
        modified=modified,
        untracked=untracked,
        ahead=ahead,
        behind=behind,
        clean=total == 0,
        summary=summary,
    )


def recent_commits(path: Path, limit: int = 5) -> list[dict[str, str]]:
    """Return recent local commits without fetching or changing repository state."""
    if not 1 <= limit <= 50:
        raise ValueError("Commit limit must be between 1 and 50.")
    command = _run(path, "log", f"-{limit}", "--date=short", "--format=%h%x1f%ad%x1f%s")
    if command is None or command.returncode != 0:
        return []
    commits: list[dict[str, str]] = []
    for line in command.stdout.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) == 3:
            commits.append(
                {
                    "sha": parts[0],
                    "date": parts[1],
                    "subject": _clean_terminal_text(parts[2]),
                }
            )
    return commits


def inspect_details(path: Path) -> dict[str, object]:
    """Return additional read-only Git signals for a project overview."""
    status = _run(path, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status is None or status.returncode != 0:
        return {
            "available": False,
            "conflicts": 0,
            "stashes": 0,
            "staged_diff": "",
            "unstaged_diff": "",
        }
    records = status.stdout.split("\0")
    conflicts = 0
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) >= 2 and ("U" in record[:2] or record[:2] in {"AA", "DD"}):
            conflicts += 1
        if len(record) >= 2 and ("R" in record[:2] or "C" in record[:2]):
            index += 1
    stash = _run(path, "stash", "list")
    staged = _run(path, "diff", "--cached", "--stat")
    unstaged = _run(path, "diff", "--stat")
    complete = all(item is not None and item.returncode == 0 for item in (stash, staged, unstaged))
    return {
        "available": complete,
        "conflicts": conflicts,
        "stashes": len(stash.stdout.splitlines()) if stash and stash.returncode == 0 else 0,
        "staged_diff": (
            _clean_terminal_text(staged.stdout.strip()) if staged and staged.returncode == 0 else ""
        ),
        "unstaged_diff": (
            _clean_terminal_text(unstaged.stdout.strip())
            if unstaged and unstaged.returncode == 0
            else ""
        ),
    }


def branch_intelligence(path: Path) -> dict[str, object]:
    """Inspect local branches and cached upstream refs without contacting remotes.

    Remote-tracking refs are only the last locally cached state. This function
    never fetches, pulls, pushes, or changes repository state.
    """
    deadline = time.monotonic() + 15

    def run(*args: str) -> str | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        result = _run(path, *args, timeout=min(GIT_TIMEOUT_SECONDS, remaining))
        return result.stdout.strip() if result and result.returncode == 0 else None

    available = run("rev-parse", "--git-dir") is not None
    current_value = run("branch", "--show-current") or None
    current = _clean_terminal_text(current_value) if current_value else None
    detached = available and current is None
    upstream_value = run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    upstream = _clean_terminal_text(upstream_value) if upstream_value else None
    ahead = behind = None
    unpushed: list[dict[str, str]] = []
    remote_only: list[dict[str, str]] = []
    if upstream:
        counts = run("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if counts:
            values = counts.split()
            if len(values) == 2 and all(value.isdigit() for value in values):
                ahead, behind = int(values[0]), int(values[1])
        for destination, revision in (
            (unpushed, f"{upstream}..HEAD"),
            (remote_only, f"HEAD..{upstream}"),
        ):
            output = run("log", "-20", "--date=short", "--format=%h%x1f%ad%x1f%s", revision)
            if output:
                for line in output.splitlines():
                    parts = line.split(chr(31), 2)
                    if len(parts) == 3:
                        destination.append(
                            {
                                "sha": parts[0],
                                "date": parts[1],
                                "subject": _clean_terminal_text(parts[2]),
                            }
                        )

    def refs(format_string: str, namespace: str) -> list[dict[str, str]]:
        output = run("for-each-ref", f"--format={format_string}", namespace)
        items: list[dict[str, str]] = []
        if output:
            for line in output.splitlines():
                fields = line.split(maxsplit=1)
                if fields and fields[0]:
                    items.append(
                        {
                            "name": _clean_terminal_text(fields[0]),
                            "sha": fields[1] if len(fields) > 1 else "",
                        }
                    )
        return items

    local_branches = refs("%(refname:short) %(objectname:short)", "refs/heads")
    remote_branches = refs("%(refname:short) %(objectname:short)", "refs/remotes")
    stash_output = run("stash", "list", "--format=%gd%x1f%gs") or ""
    stashes = []
    for line in stash_output.splitlines():
        fields = line.split(chr(31), 1)
        if len(fields) == 2:
            stashes.append({"ref": fields[0], "subject": _clean_terminal_text(fields[1])})

    return {
        "available": available and time.monotonic() < deadline,
        "timed_out": time.monotonic() >= deadline,
        "current_branch": current,
        "detached": detached,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "unpushed_commits": unpushed,
        "upstream_only_commits": remote_only,
        "local_branches": local_branches,
        "remote_branches": remote_branches,
        "stashes": stashes,
        "remote_refs_are_cached": True,
    }


def commit_activity(path: Path, days: int = 84) -> dict[date, int]:
    """Commits per author date over the last ``days`` days (local branches and remotes).

    Stashes and tags are deliberately excluded so the counts reflect real work.
    """
    command = _run(
        path,
        "log",
        "--branches",
        "--remotes",
        f"--since={days} days ago",
        "--date=short",
        "--format=%ad",
    )
    if command is None or command.returncode != 0:
        return {}
    counts: dict[date, int] = {}
    for line in command.stdout.splitlines():
        try:
            day = date.fromisoformat(line.strip())
        except ValueError:
            continue
        counts[day] = counts.get(day, 0) + 1
    return counts


def hot_files(path: Path, days: int = 30, limit: int = 5) -> list[tuple[str, int]]:
    """Most frequently changed paths in recent history, most changed first."""
    command = _run(
        path,
        "log",
        "--branches",
        "--remotes",
        f"--since={days} days ago",
        "--name-only",
        "--format=",
        "--no-renames",
    )
    if command is None or command.returncode != 0:
        return []
    counts = Counter(line.strip() for line in command.stdout.splitlines() if line.strip())
    return counts.most_common(limit)


_GRAPH_LINE = re.compile(
    r"^(?P<graph>[\s*|/\\_.-]*)(?P<sha>[0-9a-f]{7,40})(?: \((?P<refs>[^)]*)\))? (?P<subject>.*)$"
)


def parse_graph_line(line: str) -> tuple[str, str, list[str], str]:
    """Split a ``git log --graph --oneline --decorate`` line into
    ``(graph prefix, sha, decorations, subject)``; connector-only lines have no sha."""
    match = _GRAPH_LINE.match(line)
    if match is None:
        return line, "", [], ""
    refs = [ref.strip() for ref in (match["refs"] or "").split(",") if ref.strip()]
    return match["graph"], match["sha"], refs, match["subject"]


def commit_graph(path: Path, limit: int = 24) -> list[str]:
    """ASCII commit graph of local branches, cached remotes and HEAD (read-only)."""
    command = _run(
        path,
        "log",
        "--graph",
        "--oneline",
        "--decorate",
        "--color=never",
        "--branches",
        "--remotes",
        "HEAD",
        "-n",
        str(limit),
    )
    if command is None or command.returncode != 0:
        return []
    return [line.rstrip() for line in command.stdout.splitlines() if line.strip()]


def _status_letter(index: str, worktree: str) -> str:
    if index == "?":
        return "?"
    if "U" in (index, worktree) or (index, worktree) in (("A", "A"), ("D", "D")):
        return "U"
    if "R" in (index, worktree) or "C" in (index, worktree):
        return "R"
    if "D" in (index, worktree):
        return "D"
    if "A" in (index, worktree):
        return "A"
    return "M"


def parse_porcelain_z(raw: str) -> list[tuple[str, str]]:
    """``git status --porcelain=v1 -z`` -> ``(letter, path)`` with letters A, M, D, R, U, ?"""
    entries = raw.split("\0")
    changes: list[tuple[str, str]] = []
    position = 0
    while position < len(entries):
        entry = entries[position]
        position += 1
        if len(entry) < 4:
            continue
        index, worktree, name = entry[0], entry[1], entry[3:]
        if index in "RC":
            position += 1  # the next entry is the original path
        changes.append((_status_letter(index, worktree), name))
    return changes


def changed_files(path: Path, limit: int = 12) -> tuple[int, list[tuple[str, str]]]:
    """``(total changed, first ``limit`` changes)`` for the working tree (read-only)."""
    command = _run(path, "status", "--porcelain=v1", "-z", timeout=10)
    if command is None or command.returncode != 0:
        return 0, []
    changes = parse_porcelain_z(command.stdout)
    return len(changes), changes[:limit]
