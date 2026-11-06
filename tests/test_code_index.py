import subprocess
from pathlib import Path

from breezy_trace.code_index import PythonCodeIndex
from breezy_trace.registry import ProjectRegistry


def make_project(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Trace Test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "trace@example.invalid"],
        check=True,
        capture_output=True,
    )
    db_path = tmp_path / "trace.sqlite3"
    project = ProjectRegistry(db_path).register(root)
    return root, project, db_path


def test_indexes_python_symbols_and_imports_without_persisting_source(tmp_path: Path) -> None:
    root, project, db_path = make_project(tmp_path)
    (root / "sample.py").write_text(
        'import pathlib\nfrom collections import deque\n\n'
        'class Engine:\n'
        '    def start(self, value):\n'
        '        def inner():\n'
        '            return value\n'
        '        return inner()\n\n'
        'async def run_engine():\n'
        '    return Engine()\n',
        encoding="utf-8",
    )
    index = PythonCodeIndex(db_path)

    summary = index.index(project)
    symbols = index.search(project, "engine")
    imports = index.imports(project)

    assert summary["files_indexed"] == 1
    assert {item["qualified_name"] for item in symbols} == {
        "Engine",
        "Engine.start",
        "Engine.start.inner",
        "run_engine",
    }
    assert {item["kind"] for item in symbols} >= {"class", "method", "nested_function", "async_function"}
    assert {item["module"] for item in imports} == {"pathlib", "collections"}
    assert index.index(project)["files_unchanged"] == 1

    import sqlite3

    with sqlite3.connect(db_path) as connection:
        stored_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "code_symbols" in stored_tables
        assert "sample.py" in {
            row[0] for row in connection.execute("SELECT path FROM code_indexed_files")
        }
        assert "return value" not in str(
            connection.execute("SELECT * FROM code_symbols").fetchall()
        )


def test_reindexes_changed_files_and_removes_deleted_files(tmp_path: Path) -> None:
    root, project, db_path = make_project(tmp_path)
    source = root / "module.py"
    source.write_text("def old_name():\n    pass\n", encoding="utf-8")
    index = PythonCodeIndex(db_path)

    index.index(project)
    source.write_text("def new_name():\n    pass\n", encoding="utf-8")
    changed = index.index(project)
    assert changed["files_indexed"] == 1
    assert index.search(project, "old_name") == []
    assert len(index.search(project, "new_name")) == 1

    source.unlink()
    removed = index.index(project)
    assert removed["stale_files_removed"] == 1
    assert index.search(project, "new_name") == []


def test_records_syntax_errors_and_ignores_gitignored_files(tmp_path: Path) -> None:
    root, project, db_path = make_project(tmp_path)
    (root / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (root / "ignored.py").write_text("def should_not_appear():\n    pass\n", encoding="utf-8")
    index = PythonCodeIndex(db_path)

    summary = index.index(project)

    assert summary["syntax_errors"] == 1
    assert index.search(project, "broken") == []
    assert index.search(project, "should_not_appear") == []


def test_search_is_project_scoped_and_validates_limits(tmp_path: Path) -> None:
    root, project, db_path = make_project(tmp_path)
    (root / "a.py").write_text("def shared_name():\n    pass\n", encoding="utf-8")
    index = PythonCodeIndex(db_path)
    index.index(project)

    other_root = tmp_path / "other"
    other_root.mkdir()
    subprocess.run(["git", "init", str(other_root)], check=True, capture_output=True)
    other = ProjectRegistry(db_path).register(other_root)

    assert index.search(other, "shared_name") == []
    try:
        index.search(project, "shared_name", 0)
    except ValueError as error:
        assert "between 1 and 200" in str(error)
    else:
        raise AssertionError("Invalid search limit should fail")


def test_index_reuses_one_database_connection_for_many_files(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.code_index as code_index_module

    root, project, db_path = make_project(tmp_path)
    for number in range(12):
        (root / f"module_{number}.py").write_text(
            f"def function_{number}():\\n    return {number}\\n",
            encoding="utf-8",
        )

    original_connect = code_index_module.connect
    calls = 0

    def counting_connect(path):
        nonlocal calls
        calls += 1
        return original_connect(path)

    monkeypatch.setattr(code_index_module, "connect", counting_connect)
    summary = PythonCodeIndex(db_path).index(project)

    assert summary["files_indexed"] == 12
    assert calls == 1
