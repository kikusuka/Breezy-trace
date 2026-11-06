import asyncio
from pathlib import Path

from breezy_trace.app import TraceApp


def test_workspace_mounts_at_narrow_and_wide_terminal_sizes(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.registry as registry_module

    monkeypatch.setattr(registry_module, "database_path", lambda: tmp_path / "trace.sqlite3")

    async def exercise() -> None:
        for size in ((48, 18), (120, 36)):
            async with TraceApp().run_test(size=size) as pilot:
                await pilot.pause()
                assert pilot.app.query_one("#workspace") is not None
                assert pilot.app.query_one("#project-table") is not None

    asyncio.run(exercise())



def test_icon_navigation_buttons_switch_views(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.registry as registry_module

    monkeypatch.setattr(registry_module, "database_path", lambda: tmp_path / "trace.sqlite3")

    async def exercise() -> None:
        async with TraceApp().run_test(size=(120, 36)) as pilot:
            pilot.app.action_skip_intro()
            await pilot.pause()
            assert pilot.app.query_one("#nav-home").label.plain == "Home"
            assert pilot.app.query_one("#nav-code").label.plain == "Code"
            await pilot.click("#nav-journal")
            assert pilot.app.current_view == "journal"
            assert "active" in pilot.app.query_one("#nav-journal").classes
            await pilot.click("#nav-git")
            assert pilot.app.current_view == "git"
            await pilot.click("#nav-home")
            assert pilot.app.current_view == "home"

    asyncio.run(exercise())
