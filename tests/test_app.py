import asyncio
from pathlib import Path

from breezy_trace.app import TraceApp


def test_workspace_mounts_at_narrow_and_wide_terminal_sizes(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.registry as registry_module

    monkeypatch.setattr(registry_module, "database_path", lambda: tmp_path / "trace.sqlite3")

    async def exercise(size: tuple[int, int]) -> None:
        async with TraceApp().run_test(size=size) as pilot:
            await pilot.pause()
            assert pilot.app.query_one("#workspace") is not None
            assert pilot.app.query_one("#project-table") is not None

    asyncio.run(exercise((48, 18)))
    asyncio.run(exercise((120, 36)))
