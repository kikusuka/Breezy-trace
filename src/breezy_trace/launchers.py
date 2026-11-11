"""Open a project where developers work: editor, file manager, terminal.

Each launcher starts a separate program and returns immediately. Nothing is run inside
the project and no files are changed.
"""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

EDITOR_CANDIDATES = ("code", "cursor", "codium", "windsurf", "zed", "subl", "idea", "pycharm")


class LaunchError(RuntimeError):
    """The requested program could not be started."""


def editor_command(which=shutil.which, environ=None) -> list[str] | None:
    """``BREEZY_TRACE_EDITOR`` if set, else the first known editor found on PATH."""
    environ = os.environ if environ is None else environ
    configured = environ.get("BREEZY_TRACE_EDITOR", "").strip()
    if configured:
        return shlex.split(configured, posix=os.name != "nt")
    for name in EDITOR_CANDIDATES:
        found = which(name)
        if found:
            return [found]
    return None


def file_manager_name(platform: str | None = None) -> str:
    platform = platform or sys.platform
    return {"win32": "File Explorer", "darwin": "Finder"}.get(platform, "File manager")


def file_manager_command(path: Path, platform: str | None = None) -> list[str]:
    platform = platform or sys.platform
    if platform == "win32":
        return ["explorer", str(path)]
    if platform == "darwin":
        return ["open", str(path)]
    return ["xdg-open", str(path)]


def terminal_command(path: Path, platform: str | None = None, which=shutil.which) -> list[str] | None:
    platform = platform or sys.platform
    if platform == "win32":
        if which("wt"):
            return ["wt", "-d", str(path)]
        return ["cmd.exe", "/c", "start", "", "cmd.exe"]  # run with cwd=path
    if platform == "darwin":
        return ["open", "-a", "Terminal", str(path)]
    for name in ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "alacritty"):
        if which(name):
            return [name]  # run with cwd=path
    return None


def _spawn(command: list[str], cwd: Path | None = None) -> None:
    try:
        subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise LaunchError(f"Could not start {command[0]!r}: {error}") from error


def open_target(kind: str, path: Path) -> str:
    """Open ``path`` in ``kind`` (``editor``, ``folder`` or ``terminal``); returns a short
    description of what was started."""
    if kind == "editor":
        editor = editor_command()
        if editor is None:
            raise LaunchError(
                "No editor found. Install VS Code (the 'code' command) or set "
                "BREEZY_TRACE_EDITOR to your editor's command."
            )
        _spawn([*editor, str(path)])
        return f"Opened in {Path(editor[0]).stem}"
    if kind == "folder":
        _spawn(file_manager_command(path))
        return f"Opened in {file_manager_name()}"
    if kind == "terminal":
        command = terminal_command(path)
        if command is None:
            raise LaunchError("Could not find a terminal program to start.")
        _spawn(command, cwd=path)
        return "Opened a terminal here"
    raise LaunchError(f"Unknown target: {kind}")
