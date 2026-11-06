"""Benchmark cold and incremental Python indexing on a synthetic Git repository.

Run from a checkout with the development dependencies installed:
    python scripts/benchmark_index.py --files 1000
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

from breezy_trace.code_index import PythonCodeIndex
from breezy_trace.registry import ProjectRegistry


def run_git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        timeout=30,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=1000, help="Synthetic Python files to create.")
    args = parser.parse_args()
    if not 1 <= args.files <= 20_000:
        parser.error("--files must be between 1 and 20000")

    with tempfile.TemporaryDirectory(prefix="breezy-trace-benchmark-") as directory:
        base = Path(directory)
        project_root = base / "synthetic-project"
        project_root.mkdir()
        database = base / "trace.sqlite3"
        run_git(project_root, "init")

        for number in range(args.files):
            source = (
                f"import pathlib\n\n"
                f"class Component{number}:\n"
                f"    def execute(self, value: int) -> int:\n"
                f"        return value + {number}\n\n"
                f"def build_{number}():\n"
                f"    return Component{number}()\n"
            )
            (project_root / f"module_{number:05d}.py").write_text(
                source, encoding="utf-8"
            )

        project = ProjectRegistry(database).register(project_root)
        index = PythonCodeIndex(database)

        started = time.perf_counter()
        cold = index.index(project)
        cold_seconds = time.perf_counter() - started

        started = time.perf_counter()
        incremental = index.index(project)
        incremental_seconds = time.perf_counter() - started

        print(f"Files requested:       {args.files}")
        print(f"Cold indexing:         {cold_seconds:.3f}s")
        print(f"Incremental indexing:  {incremental_seconds:.3f}s")
        print(f"Cold summary:           {cold}")
        print(f"Incremental summary:    {incremental}")


if __name__ == "__main__":
    main()
