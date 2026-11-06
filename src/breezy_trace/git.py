"""Read-only Git inspection helpers."""

import subprocess
from pathlib import Path

from breezy_trace.models import GitStatus


def inspect_status(path: Path) -> GitStatus:
    """Read a concise Git status without changing repository state."""
    command = subprocess.run(
        ["git", "-C", str(path), "status", "--short", "--branch", "--ahead-behind"],
        capture_output=True,
        text=True,
        check=False,
    )
    if command.returncode != 0:
        reason = command.stderr.strip() or "Git status is unavailable."
        return GitStatus.unavailable(reason)

    lines = command.stdout.splitlines()
    branch_line = lines[0] if lines else "## unknown"
    branch_info = branch_line.removeprefix("## ")
    if branch_info.startswith("No commits yet on "):
        branch = branch_info.removeprefix("No commits yet on ").strip()
    else:
        branch = branch_info.split("...", 1)[0].split(" ", 1)[0]
    ahead = behind = staged = modified = untracked = 0

    if "[" in branch_line and "]" in branch_line:
        tracking = branch_line.split("[", 1)[1].split("]", 1)[0]
        for part in tracking.split(","):
            part = part.strip()
            if part.startswith("ahead "):
                ahead = int(part.removeprefix("ahead "))
            elif part.startswith("behind "):
                behind = int(part.removeprefix("behind "))

    for line in lines[1:]:
        code = line[:2]
        if code == "??":
            untracked += 1
        else:
            if code[0] not in {" ", "?"}:
                staged += 1
            if code[1] not in {" ", "?"}:
                modified += 1

    total = staged + modified + untracked
    summary = "Working tree clean" if total == 0 else (
        f"{staged} staged · {modified} modified · {untracked} untracked"
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
    command = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "log",
            f"-{limit}",
            "--date=short",
            "--format=%h%x1f%ad%x1f%s",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if command.returncode != 0:
        return []
    commits: list[dict[str, str]] = []
    for line in command.stdout.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) == 3:
            commits.append({"sha": parts[0], "date": parts[1], "subject": parts[2]})
    return commits


def inspect_details(path: Path) -> dict[str, object]:
    """Return additional read-only Git signals for a project overview."""
    status = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=False,
    )
    if status.returncode != 0:
        return {"conflicts": 0, "stashes": 0, "staged_diff": "", "unstaged_diff": ""}
    conflicts = sum(
        1 for line in status.stdout.splitlines()
        if len(line) >= 2 and ("U" in line[:2] or line[:2] in {"AA", "DD"})
    )
    stash = subprocess.run(
        ["git", "-C", str(path), "stash", "list"],
        capture_output=True, text=True, check=False,
    )
    staged = subprocess.run(
        ["git", "-C", str(path), "diff", "--cached", "--stat"],
        capture_output=True, text=True, check=False,
    )
    unstaged = subprocess.run(
        ["git", "-C", str(path), "diff", "--stat"],
        capture_output=True, text=True, check=False,
    )
    return {
        "conflicts": conflicts,
        "stashes": len(stash.stdout.splitlines()) if stash.returncode == 0 else 0,
        "staged_diff": staged.stdout.strip(),
        "unstaged_diff": unstaged.stdout.strip(),
    }


def branch_intelligence(path: Path) -> dict[str, object]:
    """Inspect local branches and cached upstream refs without contacting remotes.

    Remote-tracking refs are whatever the user's last fetch left locally; this
    function never fetches, pulls, pushes, or changes repository state.
    """
    def run(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    current = run("branch", "--show-current") or None
    detached = current is None
    upstream = run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    ahead = behind = None
    unpushed: list[dict[str, str]] = []
    remote_only: list[dict[str, str]] = []
    if upstream:
        counts = run("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if counts:
            values = counts.split()
            if len(values) == 2 and all(value.isdigit() for value in values):
                ahead, behind = int(values[0]), int(values[1])
        for destination, revision in ((unpushed, f"{upstream}..HEAD"), (remote_only, f"HEAD..{upstream}")):
            output = run("log", "-20", "--date=short", "--format=%h%x1f%ad%x1f%s", revision)
            if output:
                for line in output.splitlines():
                    parts = line.split("\\x1f", 2)
                    if len(parts) == 3:
                        destination.append({"sha": parts[0], "date": parts[1], "subject": parts[2]})

    def refs(format_string: str, namespace: str) -> list[dict[str, str]]:
        output = run("for-each-ref", f"--format={format_string}", namespace)
        items: list[dict[str, str]] = []
        if output:
            for line in output.splitlines():
                fields = line.split("\\t")
                if fields and fields[0]:
                    items.append({"name": fields[0], "sha": fields[1] if len(fields) > 1 else ""})
        return items

    local_branches = refs("%(refname:short)%09%(objectname:short)", "refs/heads")
    remote_branches = refs("%(refname:short)%09%(objectname:short)", "refs/remotes")
    stash_output = run("stash", "list", "--format=%gd%x1f%gs") or ""
    stashes = []
    for line in stash_output.splitlines():
        fields = line.split("\\x1f", 1)
        if len(fields) == 2:
            stashes.append({"ref": fields[0], "subject": fields[1]})

    return {
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
