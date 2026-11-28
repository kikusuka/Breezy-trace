"""Tests for standalone binaries: frozen detection, update refusal, self-test."""

import importlib.util
import sys
import sysconfig
from pathlib import Path

import pytest

from breezy_trace import cli, updater


def _notices_module():
    path = Path(__file__).resolve().parents[1] / "packaging" / "make_notices.py"
    spec = importlib.util.spec_from_file_location("make_notices", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_binary_is_detected_as_standalone(monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", "C:/Temp/_MEI123", raising=False)

    assert updater.detect_install_method() is updater.InstallMethod.STANDALONE


def test_standalone_install_has_a_clear_label():
    label = updater.describe_install_method(updater.InstallMethod.STANDALONE)

    assert "standalone" in label


def test_update_refuses_to_self_update_a_standalone_install(monkeypatch, capsys):
    monkeypatch.setattr(updater, "detect_install_method", lambda: updater.InstallMethod.STANDALONE)

    assert updater.run_update(check=False, assume_yes=True) == 1

    error = capsys.readouterr().err.lower()
    assert "standalone" in error
    assert "self-update is not supported" in error
    assert "download" in error
    assert "re-run" in error


def test_cli_self_test_boots_the_real_tui(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["breezy-trace", "--self-test"])

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 0
    assert "self-test OK" in capsys.readouterr().out


def test_cli_self_test_reports_failures(monkeypatch, capsys):
    class BrokenApp:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("simulated broken bundle")

    import breezy_trace.app as app_module

    monkeypatch.setattr(app_module, "TraceApp", BrokenApp)

    assert cli._run_self_test() == 1
    assert "self-test failed: simulated broken bundle" in capsys.readouterr().err


def test_notice_licence_normalization():
    notices = _notices_module()

    assert notices.normalize_licence("MIT") == "MIT"
    assert notices.normalize_licence("mit license") == "MIT"
    assert notices.normalize_licence("PSF-2.0") == "PSF"
    assert notices.normalize_licence("BSD-3-Clause") == "BSD-3-Clause"
    assert notices.normalize_licence("GPL-3.0") is None
    assert notices.normalize_licence("MIT OR Apache-2.0") is None


def test_notice_licence_check_rejects_unlisted_licence():
    notices = _notices_module()

    with pytest.raises(SystemExit) as error:
        notices.validate_licence("example", "GPL-3.0")

    assert "not on the allow-list" in str(error.value)


def test_notices_cover_the_bundle_and_fixed_components():
    pytest.importorskip("PyInstaller")
    notices = _notices_module()

    packages = notices.collect_packages()
    names = {package.name for package in packages}
    assert {"breezy-trace", "textual", "rich", "platformdirs"} <= names

    rendered = notices.render_notices(packages)
    assert "Python runtime" in rendered
    assert "Licence: PSF" in rendered
    assert "PyInstaller bootloader" in rendered
    assert "GPL-2.0 with PyInstaller bootloader exception" in rendered


def test_python_runtime_licence_discovery_order(tmp_path, monkeypatch):
    """The licence file is found at the first matching path in search order."""
    notices = _notices_module()

    base = tmp_path / "base"
    base.mkdir()
    stdlib = tmp_path / "stdlib"
    stdlib.mkdir()
    exe_parent = tmp_path / "exe_parent"
    exe_parent.mkdir()

    # Only stdlib's parent (tmp_path) has a LICENSE.txt
    (tmp_path / "LICENSE.txt").write_text("parent licence", encoding="utf-8")

    monkeypatch.setattr(sys, "base_prefix", str(base))
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(stdlib))
    monkeypatch.setattr(sys, "executable", str(exe_parent / "python.exe"))

    runtime = notices._python_runtime()
    assert runtime.text == "parent licence"


def test_python_runtime_licence_vendored_fallback(tmp_path, monkeypatch):
    """When no system licence file exists, the vendored copy is used."""
    notices = _notices_module()

    base = tmp_path / "base"
    base.mkdir()
    stdlib = tmp_path / "stdlib"
    stdlib.mkdir()
    exe_parent = tmp_path / "exe_parent"
    exe_parent.mkdir()

    monkeypatch.setattr(sys, "base_prefix", str(base))
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(stdlib))
    monkeypatch.setattr(sys, "executable", str(exe_parent / "python.exe"))

    runtime = notices._python_runtime()
    assert runtime.text.strip()  # vendored copy has content


def test_validate_licence_unknown_third_party_fails():
    """Unknown third-party licences still fail the build."""
    notices = _notices_module()

    with pytest.raises(SystemExit) as error:
        notices.validate_licence("example", "GPL-3.0")

    assert "not on the allow-list" in str(error.value)
