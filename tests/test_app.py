import asyncio
import subprocess
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
            await pilot.click("#nav-journal")
            assert pilot.app.current_view == "journal"
            assert "active" in pilot.app.query_one("#nav-journal").classes
            await pilot.click("#nav-git")
            assert pilot.app.current_view == "git"
            await pilot.click("#nav-home")
            assert pilot.app.current_view == "home"

    asyncio.run(exercise())



def test_open_project_registers_and_opens_selected_git_repository(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.registry as registry_module

    monkeypatch.setattr(registry_module, "database_path", lambda: tmp_path / "trace.sqlite3")
    repository = tmp_path / "nested" / "sample-project"
    repository.mkdir(parents=True)
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True, text=True)

    async def exercise() -> None:
        async with TraceApp().run_test(size=(120, 36)) as pilot:
            pilot.app.action_skip_intro()
            pilot.app._handle_project_pick(repository)
            await pilot.pause()
            assert pilot.app.active_project is not None
            assert Path(pilot.app.active_project.path) == repository.resolve()
            assert pilot.app.current_view == "overview"
            assert len(pilot.app.registry.list_projects()) == 1

    asyncio.run(exercise())
