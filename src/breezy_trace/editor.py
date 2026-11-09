"""Write notes in your own editor ($VISUAL, then $EDITOR) and parse the result."""

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

NOTE_TEMPLATE = (
    "\n\n"
    "# --- Breezy Trace: the first line above is the note title; write details below it. ---\n"
    "# --- Lines that start with '# ---' are removed. Save and close to keep the note. ---\n"
)


class EditorError(RuntimeError):
    """The editor could not be started."""


def editor_command() -> list[str]:
    configured = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if configured:
        if os.name != "nt":
            return shlex.split(configured)
        if Path(configured).is_file():  # an unquoted path that contains spaces
            return [configured]
        parts = shlex.split(configured, posix=False)  # keeps quotes, so strip them
        return [
            part[1:-1] if len(part) > 1 and part[0] == part[-1] and part[0] in "\"'" else part
            for part in parts
        ]
    if os.name == "nt":
        return ["notepad"]
    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return [candidate]
    raise EditorError("No editor found. Set the EDITOR environment variable.")


def parse_note_text(text: str) -> tuple[str, str]:
    """First non-empty line is the title (a leading ``# `` is dropped); the rest is the body."""
    lines = [line.rstrip() for line in text.splitlines() if not line.lstrip().startswith("# ---")]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "", ""
    title = lines[0].strip()
    if title.startswith("# "):
        title = title[2:].strip()
    return title, "\n".join(lines[1:]).strip()


def edit_text(initial: str = "") -> str:
    """Open the editor on a temporary file and return what was saved."""
    command = editor_command()
    with tempfile.TemporaryDirectory(prefix="breezy-trace-") as directory:
        target = Path(directory) / "note.md"
        target.write_text(initial, encoding="utf-8")
        try:
            result = subprocess.run([*command, str(target)], check=False)
        except OSError as error:
            raise EditorError(f"Could not start {command[0]!r}: {error}") from error
        if result.returncode != 0:
            raise EditorError(f"{command[0]!r} exited with status {result.returncode}.")
        return target.read_text(encoding="utf-8")
