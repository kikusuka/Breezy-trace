"""Shell prompt segment: the current project's state in a few characters.

``breezy-trace prompt`` prints nothing outside a registered repository, so it is safe to
put in every prompt. It never starts the terminal UI (and so never imports it).
"""

from pathlib import Path

from breezy_trace.git import inspect_status
from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry
from breezy_trace.theme import changed_count, is_unavailable

SHELLS = ("powershell", "bash", "zsh", "starship")


def prompt_segment(
    registry: ProjectRegistry, cwd: Path, ascii_only: bool = True, fast: bool = False
) -> str:
    """e.g. ``cyrrus main *2 ^1 t3`` (ASCII) or ``cyrrus main ±2 ↑1 ○3`` (Unicode)."""
    project = registry.find_by_path(cwd)
    if project is None:
        return ""
    open_tasks = len(JournalStore(registry.db_path).list_tasks(project, "open"))
    tasks = ""
    if open_tasks:
        tasks = f"t{open_tasks}" if ascii_only else f"○{open_tasks}"
    if fast:
        return " ".join(part for part in (project.name, tasks) if part)

    status = inspect_status(Path(project.path))
    changes, up, down, ok = (
        ("*", "^", "v", "ok") if ascii_only else ("±", "↑", "↓", "✓")
    )
    state: list[str] = []
    if is_unavailable(status):
        state.append("?")
    else:
        if changed_count(status):
            state.append(f"{changes}{changed_count(status)}")
        if status.ahead:
            state.append(f"{up}{status.ahead}")
        if status.behind:
            state.append(f"{down}{status.behind}")
        if not state:
            state.append(ok)
    branch = "" if is_unavailable(status) else status.branch
    return " ".join(part for part in (project.name, branch, *state, tasks) if part)


_POSIX_FUNCTION = """__breezy_prompt() {
  local segment
  segment="$(breezy-trace prompt 2>/dev/null)"
  [ -n "$segment" ] && printf '[%s] ' "$segment"
}
"""

SNIPPETS: dict[str, str] = {
    "powershell": """# Add to your PowerShell profile ($PROFILE). Keeps your existing prompt.
$global:__breezyOriginalPrompt = $function:prompt
function prompt {
    $segment = & breezy-trace prompt 2>$null
    $base = & $global:__breezyOriginalPrompt
    if ($segment) { "[$segment] $base" } else { $base }
}
""",
    "bash": _POSIX_FUNCTION + """# Add to ~/.bashrc
PS1='$(__breezy_prompt)'"$PS1"
""",
    "zsh": _POSIX_FUNCTION + """# Add to ~/.zshrc
setopt PROMPT_SUBST
PROMPT='$(__breezy_prompt)'"$PROMPT"
""",
    "starship": """# Add to ~/.config/starship.toml
[custom.breezy]
command = "breezy-trace prompt"
when = true
format = "[$output]($style) "
style = "bold blue"
""",
}
