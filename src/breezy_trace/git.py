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
    branch = branch_line.removeprefix("## ").split("...")[0].split()[0]
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
