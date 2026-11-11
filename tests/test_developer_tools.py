import json
import os
import subprocess
import sys
from pathlib import Path

from breezy_trace import actions, integrate, launchers, runners
from breezy_trace.git import changed_files, parse_porcelain_z
from breezy_trace.registry import ProjectError, ProjectRegistry


class FakeKey:
    def __init__(self, registry, path):
        self.registry, self.path = registry, path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWinreg:
    """Just enough of winreg to check what would be written, on any platform."""

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.values: dict[tuple[str, str], str] = {}
        self.keys: set[str] = set()

    def CreateKey(self, root, path):
        self.keys.add(path)
        return FakeKey(self, path)

    def SetValueEx(self, key, name, _reserved, _kind, value):
        self.values[(key.path, name)] = value

    def OpenKey(self, root, path):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return FakeKey(self, path)

    def QueryValueEx(self, key, name):
        return (self.values[(key.path, name)], 1)

    def DeleteKey(self, root, path):
        if path not in self.keys:
            raise FileNotFoundError(path)
        self.keys.discard(path)


def test_explorer_menu_install_status_and_uninstall() -> None:
    reg = FakeWinreg()
    assert integrate.installed_command(reg) is None
    commands = integrate.install(reg, python=r"C:\Program Files\Py\python.exe")
    assert commands[0] == r'"C:\Program Files\Py\python.exe" -m breezy_trace open "%1"'
    assert commands[1].endswith('open "%V"')
    assert reg.values[(integrate.FOLDER_KEY, "")] == integrate.LABEL
    assert integrate.installed_command(reg) == commands[0]
    assert integrate.uninstall(reg) == 4
    assert integrate.installed_command(reg) is None
    assert integrate.uninstall(reg) == 0  # nothing left; no error


def test_editor_detection_prefers_the_environment_then_known_editors() -> None:
    assert launchers.editor_command(which=lambda name: None, environ={}) is None
    found = launchers.editor_command(which=lambda name: f"/bin/{name}" if name == "cursor" else None, environ={})
    assert found == ["/bin/cursor"]
    both = launchers.editor_command(which=lambda name: f"/bin/{name}", environ={})
    assert both == ["/bin/code"]  # VS Code first
    custom = launchers.editor_command(which=lambda name: "/bin/code", environ={"BREEZY_TRACE_EDITOR": "myedit --wait"})
    assert custom == ["myedit", "--wait"]


def test_file_manager_and_terminal_commands_per_platform() -> None:
    folder = Path("proj")
    assert launchers.file_manager_command(folder, "win32") == ["explorer", "proj"]
    assert launchers.file_manager_command(folder, "darwin") == ["open", "proj"]
    assert launchers.file_manager_command(folder, "linux") == ["xdg-open", "proj"]
    assert launchers.file_manager_name("win32") == "File Explorer"
    assert launchers.terminal_command(folder, "win32", which=lambda n: "wt.exe" if n == "wt" else None) == ["wt", "-d", "proj"]
    assert launchers.terminal_command(folder, "win32", which=lambda n: None)[:3] == ["cmd.exe", "/c", "start"]
    assert launchers.terminal_command(folder, "linux", which=lambda n: None) is None


def test_open_target_starts_the_right_program_and_reports_missing_ones(tmp_path: Path, monkeypatch) -> None:
    started: list[tuple[list[str], Path | None]] = []
    monkeypatch.setattr(launchers, "_spawn", lambda command, cwd=None: started.append((command, cwd)))
    monkeypatch.setattr(launchers, "editor_command", lambda *a, **k: ["/bin/code"])
    assert launchers.open_target("editor", tmp_path) == "Opened in code"
    assert started[-1] == (["/bin/code", str(tmp_path)], None)
    assert launchers.open_target("folder", tmp_path).startswith("Opened in")
    monkeypatch.setattr(launchers, "editor_command", lambda *a, **k: None)
    try:
        launchers.open_target("editor", tmp_path)
    except launchers.LaunchError as error:
        assert "BREEZY_TRACE_EDITOR" in str(error)
    else:
        raise AssertionError("expected LaunchError")
    try:
        launchers.open_target("nonsense", tmp_path)
    except launchers.LaunchError:
        pass
    else:
        raise AssertionError("expected LaunchError")


def test_command_detection_reads_project_files(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "jest", "build": "tsc", "weird name": "x", "deploy": "y"}}),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("test:\n\tpytest\nbuild: deps\n\techo\nVAR := 1\n", encoding="utf-8")
    (tmp_path / "App.csproj").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "gradlew.bat").write_text("", encoding="utf-8")
    (tmp_path / "app" / "src" / "main").mkdir(parents=True)
    (tmp_path / "app" / "src" / "main" / "AndroidManifest.xml").write_text("<m/>", encoding="utf-8")

    found = runners.detect_commands(tmp_path, platform="win32")
    labels = [command.label for command in found]
    assert labels[:2] == ["pytest", "ruff check"]
    assert "yarn test" in labels and "yarn build" in labels
    assert "yarn deploy" not in labels and not any("weird" in label for label in labels)
    assert {"cargo test", "cargo build", "cargo clippy", "go test", "go build"} <= set(labels)
    assert "make test" in labels and "make build" in labels and "make VAR" not in labels
    assert "dotnet test" in labels
    assert labels.count("gradle assembleDebug") == 1  # Android project
    gradle = next(c for c in found if c.label == "gradle test")
    assert gradle.args[0] == str(tmp_path / "gradlew.bat")
    assert next(c for c in found if c.label == "yarn test").args == ("yarn", "run", "test")
    assert runners.detect_commands(tmp_path / "empty-nope") == []


def test_resolve_executable_uses_path_lookup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runners.shutil, "which", lambda name: "/opt/npm.cmd" if name == "npm" else None)
    assert runners.resolve_executable(runners.RunCommand("npm test", ("npm", "run", "test"), "x")) == [
        "/opt/npm.cmd", "run", "test",
    ]
    assert runners.resolve_executable(runners.RunCommand("x", ("nope", "--v"), "x")) is None
    absolute = runners.RunCommand("g", (str(tmp_path / "gradlew"), "test"), "x")
    assert runners.resolve_executable(absolute) == [str(tmp_path / "gradlew"), "test"]


def test_porcelain_parsing_handles_every_status_and_renames() -> None:
    raw = " M a.py\0A  b.py\0 D c.py\0?? d.txt\0R  new.py\0old.py\0UU e.py\0MM f.py\0"
    assert parse_porcelain_z(raw) == [
        ("M", "a.py"), ("A", "b.py"), ("D", "c.py"), ("?", "d.txt"),
        ("R", "new.py"), ("U", "e.py"), ("M", "f.py"),
    ]
    assert parse_porcelain_z("") == []


def _git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com"}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env)


def test_changed_files_lists_the_real_working_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "keep.py").write_text("1\n", encoding="utf-8")
    (repo / "drop.py").write_text("1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "x")
    (repo / "keep.py").write_text("2\n", encoding="utf-8")
    (repo / "drop.py").unlink()
    (repo / "new file.txt").write_text("hi", encoding="utf-8")
    total, changes = changed_files(repo)
    assert total == 3
    assert sorted(changes) == [("?", "new file.txt"), ("D", "drop.py"), ("M", "keep.py")]
    assert changed_files(repo, limit=1)[0] == 3 and len(changed_files(repo, limit=1)[1]) == 1
    assert changed_files(tmp_path / "missing") == (0, [])


def test_pasted_paths_are_cleaned() -> None:
    assert actions.clean_path_text('  "C:\\Users\\DELL\\My Project"  ') == "C:\\Users\\DELL\\My Project"
    assert actions.clean_path_text("'/home/me/proj'") == "/home/me/proj"
    assert actions.clean_path_text("plain") == "plain"
    assert actions.clean_path_text('"') == '"'


def test_open_from_explorer_reuses_registers_or_asks_before_initialising(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "trace.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, text=True)
    asked: list[str] = []

    first = actions.resolve_open_target(registry, Path(f'"{repo}"'), lambda m: asked.append(m) or True)
    assert first.name == "repo" and asked == []  # a Git repository needs no question
    assert actions.resolve_open_target(registry, repo, lambda m: False).id == first.id
    nested = repo / "deep" / "dir"
    nested.mkdir(parents=True)
    assert actions.resolve_open_target(registry, nested, lambda m: False).id == first.id

    plain = tmp_path / "plain-folder"
    plain.mkdir()
    (plain / "notes.txt").write_text("mine", encoding="utf-8")
    try:
        actions.resolve_open_target(registry, plain, lambda m: asked.append(m) or False)
    except ProjectError as error:
        assert "Cancelled" in str(error)
    else:
        raise AssertionError("expected ProjectError")
    assert "not a Git repository" in asked[0] and not (plain / ".git").exists()
    adopted = actions.resolve_open_target(registry, plain, lambda m: True)
    assert (plain / ".git").is_dir() and adopted.name == "plain-folder"
    assert (plain / "notes.txt").read_text(encoding="utf-8") == "mine"  # files untouched
    try:
        actions.resolve_open_target(registry, tmp_path / "missing", lambda m: True)
    except ProjectError:
        pass
    else:
        raise AssertionError("expected ProjectError")


def test_cli_integrate_is_windows_only_and_open_rejects_missing_folders(tmp_path: Path) -> None:
    data = tmp_path / "data"
    env = {**os.environ, "BREEZY_TRACE_DATA_DIR": str(data), "XDG_DATA_HOME": str(data),
           "LOCALAPPDATA": str(data), "APPDATA": str(data), "HOME": str(tmp_path)}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src") + os.pathsep + env.get("PYTHONPATH", "")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "breezy_trace", *args], check=False, cwd=tmp_path,
                              env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    missing = run("open", str(tmp_path / "nope"))
    assert missing.returncode == 1 and "error:" in missing.stderr
    if sys.platform != "win32":
        status = run("integrate", "status")
        assert status.returncode == 1 and "only available on Windows" in status.stderr
