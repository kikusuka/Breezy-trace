import os
import subprocess
import sys
from pathlib import Path

from breezy_trace import actions, editor
from breezy_trace.depgraph import build_dependency_graph, module_map
from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectRegistry

FILES = [
    "src/pkg/__init__.py",
    "src/pkg/app.py",
    "src/pkg/git.py",
    "src/pkg/util.py",
    "src/pkg/sub/__init__.py",
    "src/pkg/sub/deep.py",
    "tools/run.py",
]


def test_module_map_uses_package_structure() -> None:
    mapping = module_map(FILES)
    assert mapping["pkg"] == "src/pkg/__init__.py"
    assert mapping["pkg.git"] == "src/pkg/git.py"
    assert mapping["pkg.sub.deep"] == "src/pkg/sub/deep.py"
    assert mapping["run"] == "tools/run.py"
    assert "git" not in mapping and "src.pkg.git" not in mapping


def test_graph_resolves_absolute_and_relative_imports_and_ignores_external() -> None:
    graph = build_dependency_graph(
        FILES,
        [
            ("src/pkg/app.py", "pkg.git"),
            ("src/pkg/app.py", "git"),  # third-party GitPython, not pkg/git.py
            ("src/pkg/app.py", "os.path"),
            ("src/pkg/app.py", ".util"),
            ("src/pkg/util.py", "pkg.git.something"),
            ("src/pkg/sub/deep.py", "..util"),
            ("src/pkg/sub/deep.py", "."),  # its own package
            ("src/pkg/git.py", "pkg.app"),  # creates a cycle app -> git -> app
            ("tools/run.py", "pkg.app"),
        ],
    )
    app, git, util = "src/pkg/app.py", "src/pkg/git.py", "src/pkg/util.py"
    assert graph.edges[app] == {git, util}
    assert graph.edges[util] == {git}
    assert graph.edges["src/pkg/sub/deep.py"] == {util, "src/pkg/sub/__init__.py"}
    assert graph.edges["tools/run.py"] == {app}
    assert graph.edge_count == 7
    assert graph.cycles() == [["pkg.app", "pkg.git", "pkg.util"]]


def test_entry_points_fan_in_and_tree_rendering() -> None:
    graph = build_dependency_graph(
        FILES,
        [
            ("tools/run.py", "pkg.app"),
            ("src/pkg/app.py", "pkg.git"),
            ("src/pkg/app.py", "pkg.util"),
            ("src/pkg/util.py", "pkg.git"),
        ],
    )
    assert graph.entry_points() == ["tools/run.py"]
    assert graph.fan_in()["src/pkg/git.py"] == 2
    rows = graph.tree("tools/run.py", max_depth=3)
    assert rows[0] == ("", "run", "")
    labels = [(prefix, name) for prefix, name, _ in rows]
    assert labels[1] == ("└─ ", "pkg.app")
    assert ("   ├─ ", "pkg.git") in labels and ("   └─ ", "pkg.util") in labels
    cyclic = build_dependency_graph(FILES, [("src/pkg/app.py", "pkg.git"), ("src/pkg/git.py", "pkg.app")])
    notes = [note for _p, _n, note in cyclic.tree("src/pkg/app.py")]
    assert "cycle" in notes
    wide = build_dependency_graph(
        ["a.py", "b.py", "c.py", "d.py"], [("a.py", "b"), ("a.py", "c"), ("a.py", "d")]
    )
    assert wide.tree("a.py", max_children=2)[-1][1] == "+1 more"


def test_note_text_parsing() -> None:
    assert editor.parse_note_text("") == ("", "")
    assert editor.parse_note_text(editor.NOTE_TEMPLATE) == ("", "")
    text = "\n# Picker plan\nwide layout first\n\nthen the dialog\n# --- hint ---\n"
    assert editor.parse_note_text(text) == ("Picker plan", "wide layout first\n\nthen the dialog")
    assert editor.parse_note_text("Just a title\n") == ("Just a title", "")


def test_edit_text_runs_the_configured_editor(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "fake_editor.py"
    script.write_text(
        "import sys\n"
        "path = sys.argv[1]\n"
        "text = open(path, encoding='utf-8').read()\n"
        "open(path, 'w', encoding='utf-8').write('Edited title\\nbody line\\n' + text)\n",
        encoding="utf-8",
    )
    failing = tmp_path / "failing_editor.py"
    failing.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    old = {k: os.environ.get(k) for k in ("VISUAL", "EDITOR")}
    os.environ.pop("VISUAL", None)
    os.environ["EDITOR"] = f'"{sys.executable}" "{script}"'  # quoted: paths may contain spaces
    try:
        saved = editor.edit_text(editor.NOTE_TEMPLATE)
        title, body = editor.parse_note_text(saved)
        assert title == "Edited title" and body == "body line"
        os.environ["EDITOR"] = f'"{sys.executable}" "{failing}"'
        try:
            editor.edit_text("x")
        except editor.EditorError as error:
            assert "status 3" in str(error)
        else:
            raise AssertionError("expected EditorError")
        os.environ["EDITOR"] = "definitely-not-an-editor-xyz"
        try:
            editor.edit_text("x")
        except editor.EditorError as error:
            assert "Could not start" in str(error)
        else:
            raise AssertionError("expected EditorError")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    (path / "app.py").write_text("# TODO: first thing\nx = 1\n# FIXME: second thing\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True, text=True)
    return path


def test_import_todos_creates_tasks_once(tmp_path: Path) -> None:
    db = tmp_path / "trace.sqlite3"
    registry = ProjectRegistry(db)
    project = registry.register(_repo(tmp_path / "proj"))
    message = actions.import_todos(db, project)
    assert message.startswith("Imported 2 tasks")
    titles = sorted(row["title"] for row in JournalStore(db).list_tasks(project))
    assert titles == ["# FIXME: second thing  [app.py]", "# TODO: first thing  [app.py]"]
    again = actions.import_todos(db, project)
    assert again.startswith("Imported 0 tasks") and "2 already tracked" in again
    (tmp_path / "proj" / "more.py").write_text("\n".join(f"# TODO: item {i}" for i in range(5)), encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path / "proj"), "add", "."], check=True, capture_output=True, text=True)
    capped = actions.import_todos(db, project, limit=3)
    assert "Imported 3 tasks" in capped and "2 more waiting" in capped


def test_test_paths_are_recognised() -> None:
    from breezy_trace.depgraph import is_test_path

    assert is_test_path("tests/test_app.py") and is_test_path("pkg/tests/helpers.py")
    assert is_test_path("pkg/thing_test.py") and not is_test_path("src/pkg/app.py")
