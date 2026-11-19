import io
import sys
from pathlib import Path

import pytest

from breezy_trace import updater


class FakeDistribution:
    def __init__(self, direct_url: str | None = None) -> None:
        self.direct_url = direct_url

    def read_text(self, name: str) -> str | None:
        if name == "direct_url.json":
            return self.direct_url
        return None


def _module_path(tmp_path: Path) -> Path:
    return tmp_path / "venv" / "lib" / "breezy_trace" / "updater.py"


def _detect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    prefix: Path,
    distribution: FakeDistribution | None = None,
) -> updater.InstallMethod:
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(updater, "_distribution", lambda: distribution)
    return updater.detect_install_method(module_path=_module_path(tmp_path))


def test_detects_uv_tool_install(monkeypatch, tmp_path):
    method = _detect(
        monkeypatch,
        tmp_path,
        tmp_path / "uv" / "tools" / "breezy-trace",
        FakeDistribution(),
    )
    assert method is updater.InstallMethod.UV_TOOL


def test_detects_custom_uv_tool_dir(monkeypatch, tmp_path):
    tool_dir = tmp_path / "custom-tools"
    monkeypatch.setenv("UV_TOOL_DIR", str(tool_dir))
    method = _detect(
        monkeypatch,
        tmp_path,
        tool_dir / "breezy-trace",
        FakeDistribution(),
    )
    assert method is updater.InstallMethod.UV_TOOL


def test_detects_pipx_install(monkeypatch, tmp_path):
    method = _detect(
        monkeypatch,
        tmp_path,
        tmp_path / "pipx" / "venvs" / "breezy-trace",
        FakeDistribution(),
    )
    assert method is updater.InstallMethod.PIPX


def test_detects_custom_pipx_home(monkeypatch, tmp_path):
    pipx_home = tmp_path / "pipx-home"
    monkeypatch.setenv("PIPX_HOME", str(pipx_home))
    method = _detect(
        monkeypatch,
        tmp_path,
        pipx_home / "venvs" / "breezy-trace",
        FakeDistribution(),
    )
    assert method is updater.InstallMethod.PIPX


def test_detects_plain_pip_install(monkeypatch, tmp_path):
    method = _detect(monkeypatch, tmp_path, tmp_path / "venv", FakeDistribution())
    assert method is updater.InstallMethod.PIP


def test_detects_editable_install(monkeypatch, tmp_path):
    distribution = FakeDistribution('{"url": "file:///checkout", "dir_info": {"editable": true}}')
    method = _detect(monkeypatch, tmp_path, tmp_path / "venv", distribution)
    assert method is updater.InstallMethod.EDITABLE


def test_invalid_direct_url_falls_back_to_pip(monkeypatch, tmp_path):
    method = _detect(monkeypatch, tmp_path, tmp_path / "venv", FakeDistribution("{"))
    assert method is updater.InstallMethod.PIP


def test_source_checkout_is_editable_without_metadata(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    module = checkout / "src" / "breezy_trace" / "updater.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    (checkout / "pyproject.toml").write_text('[project]\nname = "breezy-trace"\n', encoding="utf-8")
    monkeypatch.setattr(updater, "_distribution", lambda: None)
    assert updater.detect_install_method(module_path=module) is updater.InstallMethod.EDITABLE


def test_unknown_install_is_treated_as_editable(monkeypatch, tmp_path):
    method = _detect(monkeypatch, tmp_path, tmp_path / "venv", None)
    assert method is updater.InstallMethod.EDITABLE


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("0.1.1", "0.1.0", True),
        ("0.1.0", "0.1.0", False),
        ("0.1.0", "0.1.1", False),
        ("0.2.0rc1", "0.1.0", True),
        ("0.2.0", "0.2.0rc1", True),
        ("0.2.0rc1", "0.2.0rc2", False),
        ("0.2.0rc2", "0.2.0rc1", True),
        ("0.1.0.post1", "0.1.0", True),
        ("0.1.0", "0.1.0.post1", False),
        ("0.1.0.dev1", "0.1.0a1", False),
        ("0.1.0a1", "0.1.0.dev1", True),
        ("1.0", "0.9.9", True),
        ("1.0.0", "1.0", False),
        ("v0.1.1", "0.1.0", True),
        ("0.1.0+local", "0.1.0", False),
        ("1!0.1.0", "2.0.0", True),
    ],
)
def test_version_comparison(latest, current, expected):
    assert updater.is_newer(latest, current) is expected


def test_invalid_version_raises():
    with pytest.raises(ValueError, match="unrecognized version"):
        updater.is_newer("release", "0.1.0")


def test_fetch_latest_version_calls_pypi_once(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(b'{"info": {"version": "0.2.0"}}')

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    assert updater.fetch_latest_version() == "0.2.0"
    assert calls == [(updater.PYPI_JSON_URL, 10)]


def test_fetch_latest_version_reports_errors_without_retrying(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        raise OSError("offline")

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    with pytest.raises(updater.UpdateError, match="could not reach PyPI"):
        updater.fetch_latest_version()
    assert len(calls) == 1


def test_fetch_latest_version_rejects_unexpected_payload(monkeypatch):
    monkeypatch.setattr(updater, "urlopen", lambda url, timeout: io.BytesIO(b'{"info": {}}'))
    with pytest.raises(updater.UpdateError, match="did not report a version"):
        updater.fetch_latest_version()


def test_check_reports_newer_version(monkeypatch, capsys):
    monkeypatch.setattr(updater, "fetch_latest_version", lambda: "0.2.0")
    monkeypatch.setattr(updater, "__version__", "0.1.0")
    assert updater.check_for_update() == 0
    output = capsys.readouterr().out
    assert "0.2.0" in output
    assert "newer version" in output
    assert "breezy-trace update" in output


def test_check_reports_up_to_date(monkeypatch, capsys):
    monkeypatch.setattr(updater, "fetch_latest_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "__version__", "0.1.0")
    assert updater.check_for_update() == 0
    assert "up to date" in capsys.readouterr().out


def test_check_reports_check_failure(monkeypatch, capsys):
    def fail():
        raise updater.UpdateError("offline")

    monkeypatch.setattr(updater, "fetch_latest_version", fail)
    assert updater.check_for_update() == 1
    assert "Could not check for updates" in capsys.readouterr().err


def test_build_upgrade_command_for_uv(monkeypatch):
    monkeypatch.setattr(
        updater.shutil,
        "which",
        lambda name: r"C:\Tools\uv.exe" if name == "uv" else None,
    )
    command = updater.build_upgrade_command(updater.InstallMethod.UV_TOOL)
    assert command == [r"C:\Tools\uv.exe", "tool", "upgrade", "breezy-trace"]


def test_build_upgrade_command_for_pipx(monkeypatch):
    monkeypatch.setattr(
        updater.shutil,
        "which",
        lambda name: r"C:\Tools\pipx.exe" if name == "pipx" else None,
    )
    command = updater.build_upgrade_command(updater.InstallMethod.PIPX)
    assert command == [r"C:\Tools\pipx.exe", "upgrade", "breezy-trace"]


def test_build_upgrade_command_for_pip():
    command = updater.build_upgrade_command(updater.InstallMethod.PIP)
    assert command == [sys.executable, "-m", "pip", "install", "--upgrade", "breezy-trace"]


def test_build_upgrade_command_requires_uv(monkeypatch):
    monkeypatch.setattr(updater.shutil, "which", lambda name: None)
    with pytest.raises(updater.UpdateError, match="uv is not on PATH"):
        updater.build_upgrade_command(updater.InstallMethod.UV_TOOL)


def test_build_upgrade_command_refuses_editable():
    with pytest.raises(updater.UpdateError, match="editable development checkout"):
        updater.build_upgrade_command(updater.InstallMethod.EDITABLE)


def test_run_update_refuses_editable(monkeypatch, capsys):
    monkeypatch.setattr(updater, "detect_install_method", lambda: updater.InstallMethod.EDITABLE)
    monkeypatch.setattr(updater, "_execute_upgrade", lambda command: pytest.fail("ran upgrade"))
    assert updater.run_update(check=False, assume_yes=True) == 1
    assert "editable development checkout" in capsys.readouterr().err


def test_run_update_with_yes_runs_pip(monkeypatch, capsys):
    commands = []
    monkeypatch.setattr(updater, "detect_install_method", lambda: updater.InstallMethod.PIP)
    monkeypatch.setattr(updater, "_execute_upgrade", lambda command: commands.append(command) or 0)
    assert updater.run_update(check=False, assume_yes=True) == 0
    assert commands == [[sys.executable, "-m", "pip", "install", "--upgrade", "breezy-trace"]]
    assert "plain pip" in capsys.readouterr().out


def test_run_update_confirmation_can_cancel(monkeypatch, capsys):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    commands = []
    monkeypatch.setattr(updater, "detect_install_method", lambda: updater.InstallMethod.PIP)
    monkeypatch.setattr(updater, "_execute_upgrade", lambda command: commands.append(command) or 0)
    monkeypatch.setattr(sys, "stdin", Tty("n\n"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert updater.run_update(check=False, assume_yes=False) == 0
    assert commands == []
    assert "cancelled" in capsys.readouterr().out.lower()


def test_run_update_confirmation_can_proceed(monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    commands = []
    monkeypatch.setattr(updater, "detect_install_method", lambda: updater.InstallMethod.PIP)
    monkeypatch.setattr(updater, "_execute_upgrade", lambda command: commands.append(command) or 0)
    monkeypatch.setattr(sys, "stdin", Tty("y\n"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert updater.run_update(check=False, assume_yes=False) == 0
    assert len(commands) == 1


def test_run_update_needs_yes_without_terminal(monkeypatch, capsys):
    monkeypatch.setattr(updater, "detect_install_method", lambda: updater.InstallMethod.PIP)
    monkeypatch.setattr(updater, "_execute_upgrade", lambda command: pytest.fail("ran upgrade"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert updater.run_update(check=False, assume_yes=False) == 1
    assert "Re-run with --yes" in capsys.readouterr().err


def test_run_update_check_does_not_upgrade(monkeypatch):
    monkeypatch.setattr(updater, "check_for_update", lambda: 0)
    monkeypatch.setattr(updater, "_execute_upgrade", lambda command: pytest.fail("ran upgrade"))
    assert updater.run_update(check=True, assume_yes=False) == 0


def test_visible_helper_has_required_message_and_no_obfuscation():
    script = updater._visible_helper_command(
        [r"C:\Tools\uv.exe", "tool", "upgrade", "breezy-trace"],
        1234,
        Path(r"C:\Temp\breezy-trace-update.log"),
    )
    assert "Finishing the Breezy Trace update, this window will close itself." in script
    assert "Wait-Process -Id 1234" in script
    assert "uv.exe" in script
    assert "Tee-Object" in script
    assert "cmd.exe /d /c" in script
    assert "Running: " in script
    assert "-WindowStyle" not in script
    assert "-ExecutionPolicy" not in script
    assert "-EncodedCommand" not in script


def test_visible_helper_quotes_paths_with_spaces():
    script = updater._visible_helper_command(
        [r"C:\Program Files\uv\uv.exe", "tool", "upgrade", "breezy-trace"],
        99,
        Path(r"C:\Temp\breezy-trace-update.log"),
    )
    assert r'"C:\Program Files\uv\uv.exe" tool upgrade breezy-trace' in script


def test_start_visible_upgrade_uses_plain_powershell_command(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(updater.shutil, "which", lambda name: "/usr/bin/powershell")
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    assert updater._start_visible_upgrade(["uv", "tool", "upgrade", "breezy-trace"]) == 0
    args, kwargs = calls[0]
    assert args[0] == "/usr/bin/powershell"
    assert args[1] == "-NoProfile"
    assert args[2] == "-Command"
    assert "Finishing the Breezy Trace update" in args[3]
    assert "-WindowStyle" not in args
    assert "-ExecutionPolicy" not in args
    assert "-EncodedCommand" not in args
    assert kwargs["creationflags"] == getattr(updater.subprocess, "CREATE_NEW_CONSOLE", 0)


def test_start_visible_upgrade_prints_command_without_powershell(monkeypatch, capsys):
    monkeypatch.setattr(updater.shutil, "which", lambda name: None)
    assert updater._start_visible_upgrade(["uv", "tool", "upgrade", "breezy-trace"]) == 1
    output = capsys.readouterr().err
    assert "Close Breezy Trace" in output
    assert "uv tool upgrade breezy-trace" in output


def test_cli_update_check_does_not_create_registry(monkeypatch):
    from breezy_trace import cli

    monkeypatch.setattr(cli, "ProjectRegistry", lambda: pytest.fail("registry created"))
    monkeypatch.setattr(updater, "check_for_update", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["breezy-trace", "update", "--check"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 0


def test_cli_update_yes_maps_to_run_update(monkeypatch):
    from breezy_trace import cli

    calls = []
    monkeypatch.setattr(
        updater,
        "run_update",
        lambda check, assume_yes: calls.append((check, assume_yes)) or 0,
    )
    monkeypatch.setattr(sys, "argv", ["breezy-trace", "update", "--yes"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 0
    assert calls == [(False, True)]


def test_cli_version_does_not_use_network(monkeypatch):
    from breezy_trace import cli

    calls = []
    monkeypatch.setattr(updater, "urlopen", lambda *args, **kwargs: calls.append(1))
    monkeypatch.setattr(sys, "argv", ["breezy-trace", "--version"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 0
    assert calls == []
