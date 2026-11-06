"""Conservative, local-only Python call-site inspection.

Reports syntactic call expressions, not resolved call graph edges. Dynamic
dispatch, aliases, monkey-patching, and runtime imports make target claims unsafe.
"""
from __future__ import annotations

import ast
from pathlib import Path

from breezy_trace.code_index import MAX_FILE_BYTES, _git_python_paths
from breezy_trace.models import Project


def _callee_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _callee_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return f"{_callee_name(node.func)}(...)"
    if isinstance(node, ast.Subscript):
        return f"{_callee_name(node.value)}[...]"
    return ast.dump(node, include_attributes=False)[:160]


class _CallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.records: list[dict[str, object]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        self.records.append({
            "caller": ".".join(self.scope) or "<module>",
            "callee": _callee_name(node.func),
            "line": node.lineno,
            "resolution": "unresolved-syntax",
        })
        self.generic_visit(node)


class PythonCallGraph:
    """Scan tracked and unignored Python files for call expressions."""

    def scan(
        self, project: Project, query: str | None = None, limit: int = 100
    ) -> list[dict[str, object]]:
        if not 1 <= limit <= 500:
            raise ValueError("Call-site limit must be between 1 and 500.")
        root = Path(project.path).resolve()
        needle = query.strip().casefold() if query else None
        results: list[dict[str, object]] = []

        for relative in _git_python_paths(root):
            path = root / relative
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                if not path.resolve().is_relative_to(root) or path.stat().st_size > MAX_FILE_BYTES:
                    continue
                tree = ast.parse(path.read_bytes(), filename=relative)
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue

            visitor = _CallVisitor()
            visitor.visit(tree)
            for record in visitor.records:
                item = {"path": relative, **record}
                searchable = f"{item['caller']} {item['callee']}".casefold()
                if needle and needle not in searchable:
                    continue
                results.append(item)
                if len(results) >= limit:
                    return results
        return results
