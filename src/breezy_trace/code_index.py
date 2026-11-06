"""Opt-in Python AST indexing for local code navigation.

Only symbol names, kinds, line ranges, import names, hashes, and parse status
are stored. Source text, comments, and docstrings are never persisted.
"""

import ast
import hashlib
import io
import os
import subprocess
import threading
import tokenize
import uuid
from contextlib import closing
from pathlib import Path

from breezy_trace.database import connect
from breezy_trace.models import Project

MAX_FILE_BYTES = 1_000_000


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: list[dict[str, object]] = []
        self.imports: list[dict[str, object]] = []
        self.scope: list[tuple[str, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_symbol(node, "class")
        self.scope.append((node.name, "class"))
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, "async_function")

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        if self.scope and self.scope[-1][1] == "class":
            kind = "method" if kind == "function" else "async_method"
        elif self.scope:
            kind = "nested_function"
        self._add_symbol(node, kind)
        self.scope.append((node.name, "function"))
        self.generic_visit(node)
        self.scope.pop()

    def _add_symbol(self, node: ast.AST, kind: str) -> None:
        name = getattr(node, "name", "")
        qualified = ".".join([*(item[0] for item in self.scope), name])
        self.symbols.append({
            "name": name,
            "qualified_name": qualified,
            "kind": kind,
            "line": getattr(node, "lineno", 1),
            "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
        })

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({"module": alias.name, "line": node.lineno})

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = ("." * node.level) + (node.module or "")
        self.imports.append({"module": module, "line": node.lineno})


MAX_DISCOVERED_PATHS = 100_000
MAX_DISCOVERY_OUTPUT_BYTES = 64 * 1024 * 1024
DISCOVERY_TIMEOUT_SECONDS = 30


def git_source_paths(root: Path, suffixes: set[str]) -> list[str]:
    """Stream Git paths with strict time, output, and candidate-count bounds."""
    command = ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (FileNotFoundError, OSError) as error:
        raise RuntimeError("Git file discovery is unavailable.") from error

    timed_out = threading.Event()
    timer = threading.Timer(
        DISCOVERY_TIMEOUT_SECONDS,
        lambda: (timed_out.set(), process.kill()),
    )
    timer.start()
    paths: set[str] = set()
    pending = bytearray()
    candidate_count = output_bytes = 0
    exceeded = False
    try:
        assert process.stdout is not None
        while chunk := process.stdout.read(64 * 1024):
            output_bytes += len(chunk)
            if output_bytes > MAX_DISCOVERY_OUTPUT_BYTES:
                exceeded = True
                process.kill()
                break
            pending.extend(chunk)
            while (separator := pending.find(0)) >= 0:
                item = bytes(pending[:separator])
                del pending[: separator + 1]
                if not item:
                    continue
                candidate_count += 1
                if candidate_count > MAX_DISCOVERED_PATHS:
                    exceeded = True
                    process.kill()
                    break
                decoded = item.decode("utf-8", errors="replace")
                if Path(decoded).suffix.lower() in suffixes:
                    paths.add(decoded)
            if exceeded:
                break
        return_code = process.wait()
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stdout is not None:
            process.stdout.close()

    if timed_out.is_set():
        raise RuntimeError("Git file discovery timed out after 30 seconds.")
    if exceeded:
        raise RuntimeError(
            "Git file discovery exceeded its safety limit "
            f"({MAX_DISCOVERED_PATHS:,} paths or "
            f"{MAX_DISCOVERY_OUTPUT_BYTES // (1024 * 1024)} MiB of output). "
            "Narrow the project or index a smaller repository."
        )
    if return_code != 0:
        raise RuntimeError("Could not list project files with Git.")
    if pending:
        raise RuntimeError("Git returned an incomplete NUL-delimited file list.")
    return sorted(paths)


def _git_python_paths(root: Path) -> list[str]:
    return git_source_paths(root, {".py"})


class PythonCodeIndex:
    """Build and query an explicit, local-only Python symbol index."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def index(self, project: Project) -> dict[str, int]:
        root = Path(project.path).resolve()
        connection = connect(self.db_path)
        try:
            registered = connection.execute(
                "SELECT 1 FROM projects WHERE id = ? AND path = ?",
                (project.id, str(root)),
            ).fetchone()
            if not registered:
                raise ValueError("Project is not registered in this Breezy Trace database.")

            candidates = _git_python_paths(root)
            current_paths: set[str] = set()
            indexed = unchanged = syntax_errors = skipped = 0

            for relative in candidates:
                path = root / relative
                try:
                    if path.is_symlink() or not path.is_file():
                        skipped += 1
                        continue
                    resolved = path.resolve()
                    if not resolved.is_relative_to(root):
                        skipped += 1
                        continue
                    if path.stat().st_size > MAX_FILE_BYTES:
                        skipped += 1
                        continue
                    raw = path.read_bytes()
                except OSError:
                    skipped += 1
                    continue

                current_paths.add(relative)
                digest = hashlib.sha256(raw).hexdigest()
                previous = connection.execute(
                    "SELECT content_hash FROM code_indexed_files WHERE project_id = ? AND path = ?",
                    (project.id, relative),
                ).fetchone()
                if previous and previous["content_hash"] == digest:
                    unchanged += 1
                    continue

                try:
                    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                    source = raw.decode(encoding)
                    tree = ast.parse(source, filename=relative)
                    visitor = _SymbolVisitor()
                    visitor.visit(tree)
                    parse_error = None
                except (SyntaxError, UnicodeDecodeError, LookupError) as error:
                    visitor = _SymbolVisitor()
                    parse_error = (
                        f"{error.msg} (line {error.lineno})"
                        if isinstance(error, SyntaxError)
                        else str(error)
                    )
                    syntax_errors += 1

                with connection:
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
                        (project_id, path, content_hash, indexed_at, parse_error)
                        VALUES (?, ?, ?, datetime('now'), ?)
                        ON CONFLICT(project_id, path) DO UPDATE SET
                            content_hash = excluded.content_hash,
                            indexed_at = excluded.indexed_at,
                            parse_error = excluded.parse_error
                        """,
                        (project.id, relative, digest, parse_error),
                    )
                    if parse_error is None:
                        connection.executemany(
                            """
                            INSERT INTO code_symbols
                            (id, project_id, path, name, qualified_name, kind, line, end_line)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                (
                                    uuid.uuid4().hex, project.id, relative, item["name"],
                                    item["qualified_name"], item["kind"], item["line"], item["end_line"],
                                )
                                for item in visitor.symbols
                            ],
                        )
                        connection.executemany(
                            """
                            INSERT INTO code_imports (project_id, path, module, line)
                            VALUES (?, ?, ?, ?)
                            """,
                            [
                                (project.id, relative, item["module"], item["line"])
                                for item in visitor.imports
                            ],
                        )
                indexed += 1

            rows = connection.execute(
                "SELECT path FROM code_indexed_files WHERE project_id = ? AND language = 'python'",
                (project.id,),
            ).fetchall()
            stale = [row["path"] for row in rows if row["path"] not in current_paths]
            with connection:
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
        finally:
            connection.close()

    def search(self, project: Project, query: str, limit: int = 50) -> list[dict[str, object]]:
        term = query.strip()
        if not term:
            raise ValueError("Search query cannot be empty.")
        if not 1 <= limit <= 200:
            raise ValueError("Code search limit must be between 1 and 200.")
        with closing(connect(self.db_path)) as connection, connection:
            registered = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
            if not registered:
                raise ValueError("Project is not registered in this Breezy Trace database.")
            rows = connection.execute(
                """
                SELECT path, name, qualified_name, kind, line, end_line, language
                FROM code_symbols
                WHERE project_id = ? AND (
                    name LIKE ? COLLATE NOCASE OR qualified_name LIKE ? COLLATE NOCASE
                )
                ORDER BY path, line LIMIT ?
                """,
                (project.id, f"%{term}%", f"%{term}%", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def imports(self, project: Project, query: str | None = None, limit: int = 100) -> list[dict[str, object]]:
        if not 1 <= limit <= 500:
            raise ValueError("Import list limit must be between 1 and 500.")
        with closing(connect(self.db_path)) as connection, connection:
            if query:
                rows = connection.execute(
                    """
                    SELECT path, module, line, language FROM code_imports
                    WHERE project_id = ? AND module LIKE ? COLLATE NOCASE
                    ORDER BY path, line LIMIT ?
                    """,
                    (project.id, f"%{query.strip()}%", limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT path, module, line, language FROM code_imports
                    WHERE project_id = ? ORDER BY path, line LIMIT ?
                    """,
                    (project.id, limit),
                ).fetchall()
        return [dict(row) for row in rows]
