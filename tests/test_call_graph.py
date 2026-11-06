import subprocess
from pathlib import Path

from breezy_trace.call_graph import PythonCallGraph
from breezy_trace.registry import ProjectRegistry


def test_reports_call_sites_without_claiming_target_resolution(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    source = root / "sample.py"
    source.write_text(
        "def helper():\n    pass\n\n"
        "class Worker:\n"
        "    def run(self):\n"
        "        helper()\n"
        "        service.execute(3)\n",
        encoding="utf-8",
    )
    project = ProjectRegistry(tmp_path / "trace.sqlite3").register(root)
    records = PythonCallGraph().scan(project)

    assert [(item["caller"], item["callee"]) for item in records] == [
        ("Worker.run", "helper"),
        ("Worker.run", "service.execute"),
    ]
    assert all(item["resolution"] == "unresolved-syntax" for item in records)
    assert PythonCallGraph().scan(project, query="service") == [records[1]]
