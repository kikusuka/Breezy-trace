"""Python import graph: which of a project's own modules import which.

Built from the symbol/import index (no source is re-read) using package structure
(``__init__.py``) rather than guesswork, so ``import git`` is not mistaken for a local
``pkg/git.py``. Third-party and standard-library imports are ignored. Relative imports
are resolved. This is a map of *imports*, not of calls: it says "module A imports
module B", which is reliable, and nothing about which functions run.
"""

import posixpath
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field


def module_map(files: Iterable[str]) -> dict[str, str]:
    """Dotted module name -> file path, using ``__init__.py`` to find package roots."""
    paths = sorted(path for path in files if path.endswith(".py"))
    package_dirs = {
        posixpath.dirname(path) for path in paths if posixpath.basename(path) == "__init__.py"
    }
    mapping: dict[str, str] = {}
    for path in paths:
        stem = posixpath.basename(path)[:-3]
        parts = [] if stem == "__init__" else [stem]
        directory = posixpath.dirname(path)
        while directory and directory in package_dirs:
            parts.insert(0, posixpath.basename(directory))
            directory = posixpath.dirname(directory)
        name = ".".join(parts)
        if name:
            mapping.setdefault(name, path)
    return mapping


def _resolve(
    imported: str, importer_name: str, importer_is_package: bool, mapping: dict[str, str]
) -> str | None:
    if imported.startswith("."):
        level = len(imported) - len(imported.lstrip("."))
        rest = imported.lstrip(".")
        base = importer_name.split(".") if importer_name else []
        if not importer_is_package:
            base = base[:-1]
        if level > 1:
            base = base[: max(0, len(base) - (level - 1))]
        target = ".".join(base + ([rest] if rest else []))
        return mapping.get(target)
    pieces = imported.split(".")
    for size in range(len(pieces), 0, -1):
        found = mapping.get(".".join(pieces[:size]))
        if found:
            return found
    return None


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        any(part in ("tests", "test") for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


@dataclass
class DependencyGraph:
    names: dict[str, str] = field(default_factory=dict)  # path -> dotted module name
    edges: dict[str, set[str]] = field(default_factory=dict)  # path -> imported paths

    @property
    def nodes(self) -> list[str]:
        return sorted(self.names)

    @property
    def edge_count(self) -> int:
        return sum(len(targets) for targets in self.edges.values())

    def fan_in(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for targets in self.edges.values():
            counts.update(targets)
        return counts

    def entry_points(self) -> list[str]:
        """Modules nothing else imports, busiest importers first."""
        incoming = self.fan_in()
        roots = [node for node in self.nodes if incoming[node] == 0 and self.edges.get(node)]
        return sorted(roots, key=lambda node: (-len(self.edges[node]), self.names[node]))

    def cycles(self) -> list[list[str]]:
        """Import cycles as lists of module names (strongly connected components > 1)."""
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        found: list[list[str]] = []
        counter = 0

        def visit(node: str) -> None:
            nonlocal counter
            index[node] = low[node] = counter
            counter += 1
            stack.append(node)
            on_stack.add(node)
            for target in sorted(self.edges.get(node, ())):
                if target not in index:
                    visit(target)
                    low[node] = min(low[node], low[target])
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    found.append(sorted(self.names[item] for item in component))

        for node in self.nodes:
            if node not in index:
                visit(node)
        return sorted(found)

    def tree(
        self, root: str, max_depth: int = 3, max_children: int = 5
    ) -> list[tuple[str, str, str]]:
        """Indented import tree as ``(prefix, module name, note)`` rows."""
        incoming = self.fan_in()
        rows: list[tuple[str, str, str]] = [("", self.names[root], "")]

        def walk(node: str, prefix: str, depth: int, seen: frozenset[str]) -> None:
            targets = sorted(
                self.edges.get(node, ()), key=lambda item: (-incoming[item], self.names[item])
            )
            shown = targets[:max_children]
            hidden = len(targets) - len(shown)
            for position, child in enumerate(shown):
                last = position == len(shown) - 1 and hidden == 0
                branch = "└─ " if last else "├─ "
                if child in seen:
                    rows.append((prefix + branch, self.names[child], "cycle"))
                    continue
                rows.append((prefix + branch, self.names[child], ""))
                if depth + 1 < max_depth:
                    walk(child, prefix + ("   " if last else "│  "), depth + 1, seen | {child})
            if hidden > 0:
                rows.append((prefix + "└─ ", f"+{hidden} more", "more"))

        walk(root, "", 0, frozenset({root}))
        return rows


def build_dependency_graph(
    files: Iterable[str], imports: Iterable[tuple[str, str]]
) -> DependencyGraph:
    """``files`` are indexed ``.py`` paths; ``imports`` are ``(importing path, module)``."""
    files = [path for path in files if path.endswith(".py")]
    mapping = module_map(files)
    names = {path: name for name, path in mapping.items()}
    graph = DependencyGraph(names=names, edges={path: set() for path in names})
    for importer, imported in imports:
        if importer not in names:
            continue
        is_package = posixpath.basename(importer) == "__init__.py"
        target = _resolve(imported, names[importer], is_package, mapping)
        if target and target != importer:
            graph.edges[importer].add(target)
    return graph
