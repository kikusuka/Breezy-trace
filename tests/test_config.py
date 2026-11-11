from pathlib import Path

from breezy_trace.config import data_dir


def test_data_dir_can_be_overridden(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "custom-data"
    monkeypatch.setenv("BREEZY_TRACE_DATA_DIR", str(target))

    assert data_dir() == target
    assert target.is_dir()
