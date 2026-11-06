"""Optional Tree-sitter indexing for non-Python source files.

The parser package is an optional extra. Grammar downloads happen only after the
user explicitly runs `code index`; project source is parsed locally and never
sent to the grammar provider. Only names, imports, source locations, hashes,
and parse status are persisted.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from breezy_trace.code_index import MAX_FILE_BYTES
from breezy_trace.database import connect
from breezy_trace.models import Project

LANGUAGE_EXTENSIONS = {
    "javascript": {".js", ".mjs", ".cjs", ".jsx"},
    "typescript": {".ts", ".mts", ".cts"},
    "tsx": {".tsx"},
    "rust": {".rs"},
    "go": {".go"},
    "java": {".java"},
    "csharp": {".cs"},
    "c": {".c", ".h"},
    "cpp": {".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"},
    "ruby": {".rb"},
    "php": {".php"},
}

SYMBOL_NODES = {
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "function_item": "function",
    "struct_item": "struct",
    "enum_item": "enum",
    "trait_item": "trait",
    "impl_item": "implementation",
    "function_definition": "function",
    "class_specifier": "class",
    "namespace_definition": "namespace",
    "type_declaration": "type",
}

IMPORT_NODES = {
    "import_statement",
    "import_declaration",
    "use_declaration",
    "mod_item",
    "preproc_include",
    "using_declaration",
}


def _git_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode:
        reason = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(reason or "Could not list project files with Git.")
    return sorted(
        item.decode("utf-8", errors="replace")
        for item in result.stdout.split(b"\0")
        if item and Path(item.decode("utf-8", errors="replace")).suffix.lower()
        in {ext for extensions in LANGUAGE_EXTENSIONS.values() for ext in extensions}
    )


def _node_text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()


def _node_name(node: Any, source: bytes) -> str:
    named = node.child_by_field_name("name")
    if named is not None:
        return _node_text(named, source).strip("`'")
    for child in node.named_children:
        if child.type in {"identifier", "type_identifier", "field_identifier", "operator"}:
            return _node_text(child, source).strip("`'")
    return ""


def _extract(tree: Any, source: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []

    def walk(node: Any, scope: tuple[str, ...]) -> None:
        kind = SYMBOL_NODES.get(node.type)
        name = _node_name(node, source) if kind else ""
        next_scope = scope
        if kind and name:
            symbols.append({
                "name": name,
                "qualified_name": ".".join((*scope, name)),
                "kind": kind,
                "line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
            })
            next_scope = (*scope, name)

        if node.type in IMPORT_NODES:
            value = node.child_by_field_name("source") or node.child_by_field_name("path")
            module = _node_text(value, source) if value is not None else _node_text(node, source)
            if module:
                imports.append({"module": module, "line": node.start_point.row + 1})

        for child in node.named_children:
            walk(child, next_scope)

    walk(tree.root_node, ())
    return symbols, imports


class TreeSitterCodeIndex:
    """Index supported non-Python languages using the optional grammar pack."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @staticmethod
    def available() -> bool:
        try:
            import tree_sitter_language_pack  # noqa: F401
        except ImportError:
            return False
        return True

    def index(self, project: Project) -> dict[str, int]:
        try:
            from tree_sitter_language_pack import get_parser
        except ImportError as error:
            raise RuntimeError(
                "Multi-language indexing requires the optional extra. "
                "Install it with: pip install 'breezy-trace[code]'"
            ) from error

        root = Path(project.path).resolve()
        with connect(self.db_path) as connection:
            registered = connection.execute(
                "SELECT 1 FROM projects WHERE id = ? AND path = ?",
                (project.id, str(root)),
            ).fetchone()
        if not registered:
            raise ValueError("Project is not registered in this Breezy Trace database.")

        parser_cache: dict[str, Any] = {}
        current_paths: set[str] = set()
        indexed = unchanged = syntax_errors = skipped = 0

        for relative in _git_paths(root):
            suffix = Path(relative).suffix.lower()
            language = next(
                name for name, extensions in LANGUAGE_EXTENSIONS.items() if suffix in extensions
            )
            path = root / relative
            try:
                if path.is_symlink() or not path.is_file():
                    skipped += 1
                    continue
                if not path.resolve().is_relative_to(root) or path.stat().st_size > MAX_FILE_BYTES:
                    skipped += 1
                    continue
                raw = path.read_bytes()
            except OSError:
                skipped += 1
                continue

            current_paths.add(relative)
            digest = hashlib.sha256(raw).hexdigest()
            with connect(self.db_path) as connection:
                previous = connection.execute(
                    "SELECT content_hash FROM code_indexed_files WHERE project_id = ? AND path = ?",
                    (project.id, relative),
                ).fetchone()
            if previous and previous["content_hash"] == digest:
                unchanged += 1
                continue

            try:
                if language not in parser_cache:
                    parser_cache[language] = get_parser(language)
                parser = parser_cache[language]
                tree = parser.parse(raw)
                symbols, imports = _extract(tree, raw)
                parse_error = "syntax errors detected" if tree.root_node.has_error else None
                if parse_error:
                    syntax_errors += 1
            except Exception as error:
                symbols, imports = [], []
                parse_error = f"parser error: {error}"
                syntax_errors += 1

            with connect(self.db_path) as connection:
                connection.execute(
                    "DELETE FROM code_symbols WHERE project_id = ? AND path = ?",
                    (project.id, relative),
                )
                connection.execute(
                    "DELETE FROM code_imports WHERE project_id = ? AND path = ?",
                    (project.id, relative),
                )
                connection.execute(
                    """
                    INSERT INTO code_indexed_files
                    (project_id, path, content_hash, indexed_at, parse_error, language)
                    VALUES (?, ?, ?, datetime('now'), ?, ?)
                    ON CONFLICT(project_id, path) DO UPDATE SET
                        content_hash = excluded.content_hash,
                        indexed_at = excluded.indexed_at,
                        parse_error = excluded.parse_error,
                        language = excluded.language
                    """,
                    (project.id, relative, digest, parse_error, language),
                )
                connection.executemany(
                    """
                    INSERT INTO code_symbols
                    (id, project_id, path, name, qualified_name, kind, line, end_line, language)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            uuid.uuid4().hex, project.id, relative, item["name"],
                            item["qualified_name"], item["kind"], item["line"],
                            item["end_line"], language,
                        )
                        for item in symbols
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO code_imports (project_id, path, module, line, language)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (project.id, relative, item["module"], item["line"], language)
                        for item in imports
                    ],
                )
            indexed += 1

        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT path FROM code_indexed_files WHERE project_id = ? AND language != 'python'",
                (project.id,),
            ).fetchall()
            stale = [row["path"] for row in rows if row["path"] not in current_paths]
            for relative in stale:
                connection.execute(
                    "DELETE FROM code_indexed_files WHERE project_id = ? AND path = ?",
                    (project.id, relative),
                )
                connection.execute(
                    "DELETE FROM code_symbols WHERE project_id = ? AND path = ?",
                    (project.id, relative),
                )
                connection.execute(
                    "DELETE FROM code_imports WHERE project_id = ? AND path = ?",
                    (project.id, relative),
                )

        return {
            "files_indexed": indexed,
            "files_unchanged": unchanged,
            "syntax_errors": syntax_errors,
            "files_skipped": skipped,
            "stale_files_removed": len(stale),
        }
