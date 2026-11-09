"""Detect the commands a project already defines (tests, builds, linters, scripts).

Only well-known project files in the project root are read, and only fixed command
templates are produced: package.json script *names* are validated, never executed
as text. Nothing here runs anything; the terminal UI decides when to.
"""

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]*$")
_MAKE_TARGET = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)\s*:(?!=)", re.MULTILINE)
NODE_SCRIPTS = ("test", "build", "dev", "start", "lint", "typecheck")
MAKE_TARGETS = ("test", "check", "lint", "build", "run", "dev", "all")


@dataclass(frozen=True)
class RunCommand:
    label: str  # short name shown in lists
    args: tuple[str, ...]  # argv; the first item is resolved on PATH when it runs
    source: str  # which project file suggested it

    @property
    def display(self) -> str:
        return " ".join(self.args)


def _read(path: Path, limit: int = 300_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def detect_commands(root: Path, platform: str | None = None) -> list[RunCommand]:
    platform = platform or sys.platform
    found: list[RunCommand] = []

    pyproject = root / "pyproject.toml"
    if (
        pyproject.is_file() or (root / "pytest.ini").is_file()
        or (root / "tests").is_dir() or (root / "setup.cfg").is_file()
    ):
        found.append(RunCommand("pytest", ("python", "-m", "pytest"), "Python"))
        text = _read(pyproject)
        if "[tool.ruff" in text or (root / "ruff.toml").is_file():
            found.append(RunCommand("ruff check", ("ruff", "check", "."), "ruff config"))

    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(_read(package)).get("scripts", {})
        except (ValueError, AttributeError):
            scripts = {}
        manager = "pnpm" if (root / "pnpm-lock.yaml").is_file() else (
            "yarn" if (root / "yarn.lock").is_file() else "npm"
        )
        for name in NODE_SCRIPTS:
            if isinstance(scripts, dict) and name in scripts and _SCRIPT_NAME.match(name):
                found.append(RunCommand(f"{manager} {name}", (manager, "run", name), "package.json"))

    if (root / "Cargo.toml").is_file():
        for verb in ("test", "build", "clippy"):
            found.append(RunCommand(f"cargo {verb}", ("cargo", verb), "Cargo.toml"))

    if (root / "go.mod").is_file():
        found.append(RunCommand("go test", ("go", "test", "./..."), "go.mod"))
        found.append(RunCommand("go build", ("go", "build", "./..."), "go.mod"))

    wrapper = "gradlew.bat" if platform == "win32" else "gradlew"
    if (root / wrapper).is_file():
        tasks = ["test", "build"]
        if (root / "app" / "src" / "main" / "AndroidManifest.xml").is_file():
            tasks.insert(1, "assembleDebug")
        for task in tasks:
            found.append(RunCommand(f"gradle {task}", (str(root / wrapper), task), wrapper))

    makefile = root / "Makefile"
    if makefile.is_file():
        targets = set(_MAKE_TARGET.findall(_read(makefile)))
        for name in MAKE_TARGETS:
            if name in targets:
                found.append(RunCommand(f"make {name}", ("make", name), "Makefile"))

    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        found.append(RunCommand("dotnet test", ("dotnet", "test"), ".NET project"))
        found.append(RunCommand("dotnet build", ("dotnet", "build"), ".NET project"))
    return found


def resolve_executable(command: RunCommand) -> list[str] | None:
    """argv with the program resolved on PATH (npm -> npm.cmd on Windows), or ``None``."""
    first = command.args[0]
    resolved = first if Path(first).is_absolute() else shutil.which(first)
    return [resolved, *command.args[1:]] if resolved else None
