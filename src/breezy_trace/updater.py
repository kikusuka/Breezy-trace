"""Detect how Breezy Trace was installed and upgrade it explicitly."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from enum import StrEnum
from http.client import HTTPException
from importlib import metadata
from pathlib import Path
from urllib.request import urlopen

from breezy_trace import __version__

PYPI_JSON_URL = "https://pypi.org/pypi/breezy-trace/json"
CHECK_TIMEOUT_SECONDS = 10

_VERSION_RE = re.compile(
    r"^(?:(\d+)!)?v?(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?(?:\.post(\d+))?(?:\.dev(\d+))?$"
)

_EDITABLE_MESSAGE = (
    "Breezy Trace is running from an editable development checkout, so it cannot "
    "upgrade itself.\n"
    "Update the checkout instead:\n"
    "  git pull\n"
    '  python -m pip install -e ".[dev,code]"\n'
    "Or install a released copy with:\n"
    "  uv tool install --upgrade breezy-trace"
)


class UpdateError(RuntimeError):
    """Raised when an update cannot be checked, prepared, or started."""


class InstallMethod(StrEnum):
    """How the running Breezy Trace package was installed."""

    UV_TOOL = "uv-tool"
    PIPX = "pipx"
    PIP = "pip"
    EDITABLE = "editable"
    STANDALONE = "standalone"


def _normalized_path(value: str | Path) -> str:
    path = Path(value).expanduser()
    return os.path.normcase(os.path.abspath(str(path))).replace("\\", "/").rstrip("/")


def _is_under(child: str, parent: str) -> bool:
    return child == parent or child.startswith(f"{parent}/")


def _is_source_checkout(module_path: Path) -> bool:
    try:
        root = module_path.parents[2]
    except IndexError:
        return False
    pyproject = root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    project = data.get("project")
    return isinstance(project, dict) and project.get("name") == "breezy-trace"


def _distribution():
    try:
        return metadata.distribution("breezy-trace")
    except metadata.PackageNotFoundError:
        return None


def _direct_url(distribution) -> dict | None:
    try:
        raw = distribution.read_text("direct_url.json")
    except OSError:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _is_editable(distribution) -> bool:
    data = _direct_url(distribution)
    if not data:
        return False
    dir_info = data.get("dir_info")
    return isinstance(dir_info, dict) and dir_info.get("editable") is True


def _matches_uv_tool(prefix: str) -> bool:
    tool_dir = os.environ.get("UV_TOOL_DIR")
    if tool_dir and _is_under(prefix, _normalized_path(tool_dir)):
        return True
    return "/uv/tools/" in f"{prefix}/"


def _matches_pipx(prefix: str) -> bool:
    pipx_home = os.environ.get("PIPX_HOME")
    if pipx_home and _is_under(prefix, _normalized_path(Path(pipx_home) / "venvs")):
        return True
    return "/pipx/venvs/" in f"{prefix}/"


def detect_install_method(module_path: Path | None = None) -> InstallMethod:
    """Return how this copy of Breezy Trace was installed.

    ``module_path`` is injectable so tests can describe a location without
    moving the running package.
    """

    module = module_path or Path(__file__).resolve()
    # Check for PyInstaller/frozen binary first — takes priority over
    # any installed distribution so that frozen installs are always
    # recognised as standalone.
    if getattr(sys, "_MEIPASS", None) is not None:
        return InstallMethod.STANDALONE

    if _is_source_checkout(module):
        return InstallMethod.EDITABLE

    distribution = _distribution()
    if distribution is not None and _is_editable(distribution):
        return InstallMethod.EDITABLE

    prefix = _normalized_path(sys.prefix)
    if _matches_uv_tool(prefix):
        return InstallMethod.UV_TOOL
    if _matches_pipx(prefix):
        return InstallMethod.PIPX
    if distribution is None:
        return InstallMethod.EDITABLE
    return InstallMethod.PIP


def describe_install_method(method: InstallMethod) -> str:
    """Return a short label for a detected install method."""

    labels = {
        InstallMethod.UV_TOOL: "uv tool",
        InstallMethod.PIPX: "pipx",
        InstallMethod.PIP: "plain pip",
        InstallMethod.EDITABLE: "editable development checkout",
        InstallMethod.STANDALONE: "standalone (frozen) install",
    }
    return labels[method]


def build_upgrade_command(method: InstallMethod) -> list[str]:
    """Build the upgrade command for a detected install method."""

    if method is InstallMethod.UV_TOOL:
        uv = shutil.which("uv")
        if uv is None:
            raise UpdateError(
                "uv is not on PATH, so Breezy Trace cannot run 'uv tool upgrade'. "
                "Install uv from https://astral.sh/uv or run 'breezy-trace update' "
                "from a terminal where uv is available."
            )
        return [uv, "tool", "upgrade", "breezy-trace"]
    if method is InstallMethod.PIPX:
        pipx = shutil.which("pipx")
        if pipx is None:
            raise UpdateError(
                "pipx is not on PATH, so Breezy Trace cannot run 'pipx upgrade'. "
                "Open a terminal where pipx is available and try again."
            )
        return [pipx, "upgrade", "breezy-trace"]
    if method is InstallMethod.PIP:
        return [sys.executable, "-m", "pip", "install", "--upgrade", "breezy-trace"]
    raise UpdateError(_EDITABLE_MESSAGE)


def format_command(command: list[str]) -> str:
    """Format a command for display on the current platform."""

    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def fetch_latest_version() -> str:
    """Ask PyPI once for the latest version.

    This is the only network call in this module. It sends no cookies, query
    parameters, or body, and it never runs automatically.
    """

    try:
        with urlopen(PYPI_JSON_URL, timeout=CHECK_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except (OSError, ValueError, HTTPException) as error:
        raise UpdateError(f"could not reach PyPI ({error})") from error
    if not isinstance(payload, dict):
        raise UpdateError("PyPI returned an unexpected response.")
    info = payload.get("info")
    if not isinstance(info, dict):
        raise UpdateError("PyPI returned an unexpected response.")
    latest = info.get("version")
    if not isinstance(latest, str) or not latest.strip():
        raise UpdateError("PyPI did not report a version.")
    return latest.strip()


def _parse_version(value: str) -> tuple[int, tuple[int, ...], tuple[int, int, int]]:
    text = value.strip().lower()
    text = text.split("+", 1)[0]
    match = _VERSION_RE.fullmatch(text)
    if match is None:
        raise ValueError(f"unrecognized version: {value!r}")
    epoch = int(match.group(1) or 0)
    release = tuple(int(part) for part in match.group(2).split("."))
    prerelease = match.group(3)
    post = match.group(5)
    dev = match.group(6)
    if prerelease:
        rank = (1, {"a": 0, "b": 1, "rc": 2}[prerelease], int(match.group(4) or 0))
    elif post is not None:
        rank = (3, int(post), 0)
    elif dev is not None:
        rank = (0, int(dev), 0)
    else:
        rank = (2, 0, 0)
    return epoch, release, rank


def is_newer(latest: str, current: str) -> bool:
    """Return whether ``latest`` is a newer version than ``current``."""

    latest_epoch, latest_release, latest_rank = _parse_version(latest)
    current_epoch, current_release, current_rank = _parse_version(current)
    if latest_epoch != current_epoch:
        return latest_epoch > current_epoch
    width = max(len(latest_release), len(current_release))
    latest_padded = latest_release + (0,) * (width - len(latest_release))
    current_padded = current_release + (0,) * (width - len(current_release))
    if latest_padded != current_padded:
        return latest_padded > current_padded
    return latest_rank > current_rank


def check_for_update() -> int:
    """Check PyPI once and report whether a newer version exists."""

    try:
        latest = fetch_latest_version()
        if is_newer(latest, __version__):
            status = "A newer version is available. Update with: breezy-trace update"
        elif is_newer(__version__, latest):
            status = "Your installed version is newer than the latest PyPI release."
        else:
            status = "Breezy Trace is up to date."
    except (UpdateError, ValueError) as error:
        print(f"Could not check for updates: {error}", file=sys.stderr)
        return 1

    print(f"Installed: {__version__}")
    print(f"Latest on PyPI: {latest}")
    print(status)
    print("This check sent one request to pypi.org and no project data.")
    return 0


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _visible_helper_command(command: list[str], parent_pid: int, log_path: Path) -> str:
    command_text = subprocess.list2cmdline(command)
    log = _ps_quote(str(log_path))
    return (
        "$host.UI.RawUI.WindowTitle = 'Breezy Trace update'; "
        "Write-Host 'Finishing the Breezy Trace update, this window will close itself.'; "
        f"try {{ Wait-Process -Id {parent_pid} -Timeout 180 -ErrorAction Stop }} catch {{ }}; "
        "Start-Sleep -Seconds 1; "
        f"$log = {log}; "
        f"$line = {_ps_quote(command_text)}; "
        "Write-Host ('Running: ' + $line); "
        "& cmd.exe /d /c ($line + ' 2>&1') | Tee-Object -FilePath $log; "
        "if ($null -eq $LASTEXITCODE) { $code = 1 } else { $code = $LASTEXITCODE }; "
        "try { Add-Content -LiteralPath $log -Value ('EXIT_CODE=' + $code) } catch { }; "
        "if ($code -eq 0) { "
        "Write-Host 'Breezy Trace update finished. This window will close itself.' "
        "} else { "
        "Write-Host 'Breezy Trace update failed. See the log file. This window will close itself.' "
        "}; "
        "Start-Sleep -Seconds 3;"
    )


def _start_visible_upgrade(command: list[str]) -> int:
    powershell = shutil.which("powershell")
    if powershell is None:
        print("PowerShell was not found to finish the update.", file=sys.stderr)
        print("Close Breezy Trace and run this command yourself:", file=sys.stderr)
        print(f"  {format_command(command)}", file=sys.stderr)
        return 1

    log_path = Path(tempfile.gettempdir()) / f"breezy-trace-update-{os.getpid()}.log"
    script = _visible_helper_command(command, os.getpid(), log_path)
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    print(
        "Windows cannot replace a running program, so the upgrade will finish in a separate window."
    )
    print(f"Command: {format_command(command)}")
    print(f"Log: {log_path}")
    try:
        subprocess.Popen(
            [powershell, "-NoProfile", "-Command", script],
            creationflags=creation_flags,
            close_fds=True,
        )
    except OSError as error:
        print(f"Could not start the helper window: {error}", file=sys.stderr)
        print("Close Breezy Trace and run this command yourself:", file=sys.stderr)
        print(f"  {format_command(command)}", file=sys.stderr)
        return 1
    print("A separate window will finish the update and close itself.")
    print("When it finishes, run: breezy-trace --version")
    return 0


def _execute_upgrade(command: list[str]) -> int:
    if os.name == "nt":
        return _start_visible_upgrade(command)
    try:
        result = subprocess.run(command, check=False)
    except OSError as error:
        print(f"Could not start the upgrade: {error}", file=sys.stderr)
        print(f"Run this command yourself: {format_command(command)}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(
            f"The upgrade command failed (exit code {result.returncode}).",
            file=sys.stderr,
        )
        print(f"You can retry it manually: {format_command(command)}", file=sys.stderr)
        return result.returncode
    print("Upgrade finished. Run 'breezy-trace --version' to confirm.")
    return 0


def run_update(check: bool, assume_yes: bool) -> int:
    """Run ``breezy-trace update`` or ``breezy-trace update --check``."""

    if check:
        return check_for_update()

    try:
        method = detect_install_method()
    except Exception as error:  # noqa: BLE001 - detection must not crash the command
        print(f"Could not determine how Breezy Trace was installed: {error}", file=sys.stderr)
        return 1

    if method is InstallMethod.EDITABLE:
        print(_EDITABLE_MESSAGE, file=sys.stderr)
        return 1

    if method is InstallMethod.STANDALONE:
        print(
            "Breezy Trace is installed as a standalone (frozen) application."
            " Self-update is not supported. Download the new version from the"
            " website or re-run the installer to get the latest release.",
            file=sys.stderr,
        )
        return 1

    try:
        command = build_upgrade_command(method)
    except UpdateError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Install method: {describe_install_method(method)}")
    print(f"Upgrade command: {format_command(command)}")

    if not assume_yes:
        if not sys.stdin.isatty():
            print(
                "No interactive terminal is available for confirmation. "
                "Re-run with --yes to confirm the upgrade.",
                file=sys.stderr,
            )
            return 1
        answer = input("Proceed with the upgrade? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Upgrade cancelled.")
            return 0

    return _execute_upgrade(command)
