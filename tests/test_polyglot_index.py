from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

from breezy_trace.code_index import PythonCodeIndex
from breezy_trace.polyglot_index import TreeSitterCodeIndex
from breezy_trace.registry import ProjectRegistry


class Point:
    def __init__(self, row: int) -> None:
        self.row = row


class Node:
    def __init__(
        self, kind: str, start: int, end: int, children=None, fields=None, text: bytes = b""
    ) -> None:
        self.type = kind
        self.start_point = Point(start)
        self.end_point = Point(end)
        self.start_byte = 0
        self.end_byte = len(text)
        self.named_children = children or []
        self.fields = fields or {}

    def child_by_field_name(self, name: str):
        return self.fields.get(name)


class Parser:
    def __init__(self, tree) -> None:
        self.tree = tree

    def parse(self, _source: bytes):
        return self.tree


def make_project(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    db_path = tmp_path / "trace.sqlite3"
    project = ProjectRegistry(db_path).register(root)
    return root, project, db_path


def test_indexes_javascript_symbols_and_imports_without_real_parser_dependency(
    tmp_path: Path, monkeypatch
) -> None:
    root, project, db_path = make_project(tmp_path)
    (root / "app.js").write_text("import React from 'react';\nfunction greet() {}\n", encoding="utf-8")

    name = Node("identifier", 1, 1, text=b"greet")
    function = Node("function_declaration", 1, 1, [name], {"name": name})
    source = Node("string", 0, 0, text=b"'react'")
    import_node = Node("import_statement", 0, 0, [source], {"source": source})
    root_node = Node("program", 0, 2, [import_node, function])
    fake_pack = types.ModuleType("tree_sitter_language_pack")
    fake_pack.get_parser = lambda _language: Parser(types.SimpleNamespace(root_node=root_node))
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", fake_pack)

    summary = TreeSitterCodeIndex(db_path).index(project)

    assert summary["files_indexed"] == 1
    with __import__("sqlite3").connect(db_path) as connection:
        symbol = connection.execute(
            "SELECT name, kind, language FROM code_symbols WHERE path = 'app.js'"
        ).fetchone()
        imported = connection.execute(
            "SELECT module, language FROM code_imports WHERE path = 'app.js'"
        ).fetchone()
    assert symbol == ("greet", "function", "javascript")
    assert imported == ("'react'", "javascript")


def test_python_index_does_not_remove_other_language_rows(tmp_path: Path, monkeypatch) -> None:
    root, project, db_path = make_project(tmp_path)
    (root / "app.js").write_text("function greet() {}\n", encoding="utf-8")

    symbol = Node("identifier", 0, 0, text=b"greet")
    function = Node("function_declaration", 0, 0, [symbol], {"name": symbol})
    root_node = Node("program", 0, 0, [function])
    fake_pack = types.ModuleType("tree_sitter_language_pack")
    fake_pack.get_parser = lambda _language: Parser(types.SimpleNamespace(root_node=root_node))
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", fake_pack)

    TreeSitterCodeIndex(db_path).index(project)
    PythonCodeIndex(db_path).index(project)

    with __import__("sqlite3").connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM code_symbols WHERE path = 'app.js'"
        ).fetchone()[0]
    assert count == 1
