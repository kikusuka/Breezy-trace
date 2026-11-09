import asyncio
import subprocess
from pathlib import Path

from textual.widgets import Input

from breezy_trace import theme
from breezy_trace.app import TraceApp
from breezy_trace.intro import IntroScreen
from breezy_trace.journal import JournalStore
from breezy_trace.screens import ChoiceScreen, FormScreen, HelpScreen


async def settle(pilot) -> None:
    """Let background work (git status, view builders, jobs) finish and the screen repaint."""
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def _isolate(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.app as app_module
    import breezy_trace.registry as registry_module
    import breezy_trace.settings as settings_module

    monkeypatch.setattr(registry_module, "database_path", lambda: tmp_path / "trace.sqlite3")
    monkeypatch.setattr(settings_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module, "data_dir", lambda: tmp_path / "data")


def _init_repo(path: Path, commit: bool = False) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    if commit:
        (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@e.com",
             "commit", "-m", "first"],
            check=True, capture_output=True, text=True,
        )
    return path


def test_lobby_mounts_at_narrow_and_wide_terminal_sizes(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)

    async def exercise() -> None:
        for size in ((48, 18), (120, 36)):
            async with TraceApp(intro=False).run_test(size=size) as pilot:
                await settle(pilot)
                assert pilot.app.current_view == "home"
                assert pilot.app.query_one("#project-list").display is True
                assert pilot.app.query_one("#tabs").display is False

    asyncio.run(exercise())


def test_opening_a_project_swaps_the_window_to_the_project_page(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "nested" / "sample-project")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            pilot.app._handle_project_pick(repository)
            await settle(pilot)
            app = pilot.app
            assert Path(app.active_project.path) == repository.resolve()
            assert app.current_view == "overview"
            assert app.query_one("#project-list").display is False
            assert app.query_one("#tabs").display is True
            assert len(app.registry.list_projects()) == 1
            await pilot.press("escape")
            assert app.current_view == "home"
            assert app.query_one("#project-list").display is True
            assert app.query_one("#tabs").display is False

    asyncio.run(exercise())


def test_number_keys_and_tabs_switch_project_views(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "keys-project", commit=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            pilot.app._handle_project_pick(repository)
            await settle(pilot)
            await pilot.click("#tab-journal")
            assert pilot.app.current_view == "journal"
            assert "active" in pilot.app.query_one("#tab-journal").classes
            for key, view in (("4", "git"), ("5", "activity"), ("6", "code"),
                              ("7", "settings"), ("2", "metrics"), ("1", "overview")):
                await pilot.press(key)
                assert pilot.app.current_view == view
            await pilot.click("#tab-home")
            assert pilot.app.current_view == "home"

    asyncio.run(exercise())


def test_project_views_need_a_project_and_keys_follow_the_screen(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "keys-project")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app.action_goto("git")
            assert app.current_view == "home"
            assert app.check_action("open_project", ()) is True
            assert app.check_action("goto", ("home",)) is False
            assert app.check_action("new_note", ()) is False
            assert app.check_action("backup_data", ()) is True
            app._handle_project_pick(repository)
            await settle(pilot)
            assert app.check_action("open_project", ()) is False
            assert app.check_action("goto", ("home",)) is True
            assert app.check_action("new_note", ()) is True

    asyncio.run(exercise())


def test_resume_page_renders_at_narrow_and_wide_sizes(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "resume-project")

    async def exercise() -> None:
        for size in ((60, 24), (140, 40)):
            async with TraceApp(intro=False).run_test(size=size) as pilot:
                pilot.app._handle_project_pick(repository)
                await settle(pilot)
                project = pilot.app.active_project
                store = JournalStore(pilot.app.registry.db_path)
                store.add_task(project, "Wire up the picker")
                store.add_decision(project, "Storage", "Keep SQLite")
                pilot.app.action_goto("overview")
                await settle(pilot)
                _header, left, _right = pilot.app._parts["overview"]
                assert "Wire up the picker" in left.plain
                assert "Keep SQLite" in left.plain

    asyncio.run(exercise())


def test_metrics_tab_computes_in_the_background(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "metrics-project", commit=True)

    async def exercise() -> None:
        for size in ((60, 24), (140, 40)):
            async with TraceApp(intro=False).run_test(size=size) as pilot:
                pilot.app._handle_project_pick(repository)
                await settle(pilot)
                await pilot.press("2")
                await pilot.app.workers.wait_for_complete()
                await settle(pilot)
                project = pilot.app.active_project
                _stamp, data = pilot.app._metrics[project.id]
                assert data is not None and data.total_commits == 1
                _header, left, right = pilot.app._parts["metrics"]
                assert "1 total" in left.plain
                assert "Python" in right.plain

    asyncio.run(exercise())


def test_project_list_loads_live_git_state(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "dirty-project")
    (repository / "notes.txt").write_text("untracked\n", encoding="utf-8")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            pilot.app._handle_project_pick(repository)
            await pilot.app.workers.wait_for_complete()
            await settle(pilot)
            status = pilot.app._states[pilot.app.active_project.id]
            assert status.untracked == 1 and not status.clean

    asyncio.run(exercise())


def test_help_opens_from_anywhere_and_closes(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "help-project")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            await pilot.press("question_mark")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            assert not isinstance(app.screen, HelpScreen)
            await pilot.press("f1")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("f1")
            assert not isinstance(app.screen, HelpScreen)
            app._handle_project_pick(repository)
            await settle(pilot)
            await pilot.press("question_mark")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("q")
            assert not isinstance(app.screen, HelpScreen)
            assert app.is_running

    asyncio.run(exercise())


def test_manual_features_save_through_forms(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "forms-project")

    async def fill(pilot, **values: str) -> None:
        form = pilot.app.screen
        assert isinstance(form, FormScreen)
        for key, value in values.items():
            form.query_one(f"#field-{key}", Input).value = value
        form._save()
        await settle(pilot)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            project = app.active_project
            store = JournalStore(app.registry.db_path)

            app.action_new_note()
            await settle(pilot)
            await fill(pilot, title="First note", body="details")
            app.action_new_task()
            await settle(pilot)
            await fill(pilot, title="Ship it")
            app.action_new_decision()
            await settle(pilot)
            await fill(pilot, title="Storage", decision="SQLite", context="simple")
            assert app.screen is app._main

            assert [row["title"] for row in store.list_entries(project)] == ["First note"]
            assert [row["title"] for row in store.list_tasks(project, "open")] == ["Ship it"]
            assert [row["title"] for row in store.list_decisions(project)] == ["Storage"]

            app.action_complete_task()
            await settle(pilot)
            assert isinstance(app.screen, ChoiceScreen)
            task_id = store.list_tasks(project, "open")[0]["id"]
            app.screen.dismiss(task_id)
            await settle(pilot)
            assert store.list_tasks(project, "open") == []

    asyncio.run(exercise())


def test_required_form_fields_block_saving(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "required-project")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            pilot.app._handle_project_pick(repository)
            await settle(pilot)
            pilot.app.action_new_decision()
            await settle(pilot)
            form = pilot.app.screen
            form.query_one("#field-title", Input).value = "Only a topic"
            form._save()
            await settle(pilot)
            assert isinstance(pilot.app.screen, FormScreen)  # still open: decision missing

    asyncio.run(exercise())


def test_background_jobs_run_without_blocking(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "jobs-project", commit=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            app.action_scan_activity()
            app.action_sync_sessions()
            app.action_index_code()
            await app.workers.wait_for_complete()
            await settle(pilot)
            app.action_goto("home")
            app.action_backup_data()
            await app.workers.wait_for_complete()
            await settle(pilot)
            assert len(list((tmp_path / "data").glob("breezy-trace-backup-*.sqlite3"))) == 1

    asyncio.run(exercise())


def test_theme_switches_and_is_remembered(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "theme-project")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            assert theme.current_theme() == "sky"
            light_bg = theme.PALETTE["bg"]
            app._handle_project_pick(repository)
            await settle(pilot)
            app.action_cycle_theme()
            await settle(pilot)
            assert theme.current_theme() == "midnight" and theme.PALETTE["bg"] != light_bg
            assert app.current_view == "overview"
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            assert theme.current_theme() == "midnight"  # remembered
            pilot.app.action_cycle_theme()
            await settle(pilot)
            assert theme.current_theme() == "sky"

    asyncio.run(exercise())


def test_background_state_loads_while_the_intro_is_showing(tmp_path: Path, monkeypatch) -> None:
    """Regression: results must land on the main screen even with the intro on top."""
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "behind-the-intro")
    import breezy_trace.registry as registry_module

    registry_module.ProjectRegistry().register(repository)

    async def exercise() -> None:
        async with TraceApp(intro=True).run_test(size=(120, 36)) as pilot:
            assert isinstance(pilot.app.screen, IntroScreen)
            await pilot.app.workers.wait_for_complete()
            total, loaded, _attention, colors = pilot.app.boot_status()
            assert (total, loaded) == (1, 1)
            assert colors[0] is not None

    asyncio.run(exercise())


def test_intro_plays_on_launch_and_any_key_skips_it(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)

    async def exercise() -> None:
        async with TraceApp(intro=True).run_test(size=(120, 36)) as pilot:
            await settle(pilot)
            assert isinstance(pilot.app.screen, IntroScreen)
            await pilot.press("f1")  # help must not stack on top of the intro
            assert isinstance(pilot.app.screen, IntroScreen) or pilot.app.screen is pilot.app._main
            await pilot.press("x")
            await settle(pilot)
            assert not isinstance(pilot.app.screen, IntroScreen)
            assert pilot.app.current_view == "home"

    asyncio.run(exercise())


def test_intro_ends_by_itself_and_fits_a_small_terminal(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)

    async def exercise() -> None:
        async with TraceApp(intro=True).run_test(size=(48, 18)) as pilot:
            for _ in range(150):
                await pilot.pause(0.04)
                if not isinstance(pilot.app.screen, IntroScreen):
                    break
            assert not isinstance(pilot.app.screen, IntroScreen)

    asyncio.run(exercise())


def test_footer_keys_are_contextual_but_every_key_stays_live(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "ctx-project", commit=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            for view, shown in (("code", "index_code"), ("activity", "scan_activity"),
                                ("activity", "sync_sessions"), ("settings", "backup_data")):
                app.action_goto(view)
                assert app.check_action(shown, ()) is True
                assert app.check_action(shown + "_any", ()) is False
            app.action_goto("journal")
            for action in ("index_code", "scan_activity", "sync_sessions", "backup_data"):
                assert app.check_action(action, ()) is False
                assert app.check_action(action + "_any", ()) is True  # key still works here

    asyncio.run(exercise())


def test_search_spans_every_project_and_returns_to_the_lobby(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "search-project")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            JournalStore(app.registry.db_path).add_note(
                app.active_project, "Picker redesign", "wide layout"
            )
            app.action_search()
            await settle(pilot)
            form = app.screen
            assert isinstance(form, FormScreen)
            form.query_one("#field-query", Input).value = "picker"
            form._save()
            await settle(pilot)
            assert app.current_view == "search"
            assert app.query_one("#project-list").display is True
            assert app.query_one("#tabs").display is False
            assert len(app._last_search[1]) == 1
            assert "Picker redesign" in app._search_text().plain
            await pilot.press("escape")
            assert app.current_view == "home"

    asyncio.run(exercise())


def test_resume_shows_what_changed_since_the_project_was_last_opened(
    tmp_path: Path, monkeypatch
) -> None:
    from datetime import UTC, datetime, timedelta

    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "digest-project", commit=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(140, 40)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            project = app.active_project
            app._since[project.id] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
            app.action_goto("overview")
            await settle(pilot)
            left = app._parts["overview"][1].plain
            assert "SINCE YOU LAST OPENED" in left and "1 commit by 1 author" in left

    asyncio.run(exercise())


def test_git_and_code_tabs_render_graph_and_charts(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "graph-project", commit=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            app.action_index_code()
            await app.workers.wait_for_complete()
            await settle(pilot)
            app.action_goto("git")
            await settle(pilot)
            assert app.current_view == "git"
            assert "BRANCH GRAPH" in app._main.query_one("#content").render().plain
            app.action_goto("code")
            await settle(pilot)
            assert app.current_view == "code"

    asyncio.run(exercise())


def test_handoff_export_writes_a_markdown_file(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "handoff-project", commit=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            app.action_export_handoff()
            await app.workers.wait_for_complete()
            await settle(pilot)
            files = list((tmp_path / "data" / "handoffs").glob("handoff-handoff-project-*.md"))
            assert len(files) == 1
            assert "# handoff-project: handoff" in files[0].read_text(encoding="utf-8")

    asyncio.run(exercise())


def test_dependency_map_and_todo_import_and_editor_keys(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "deps-project")
    (repository / "pkg").mkdir()
    (repository / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repository / "pkg" / "a.py").write_text("from pkg import b\n# TODO: wire a\n", encoding="utf-8")
    (repository / "pkg" / "b.py").write_text("import os\n", encoding="utf-8")
    (repository / "main.py").write_text("import pkg.a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True, capture_output=True, text=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            app.action_index_code()
            await app.workers.wait_for_complete()
            await settle(pilot)
            app.action_goto("code")
            await settle(pilot)
            rendered = app._main.query_one("#content").render().plain
            assert "DEPENDENCY MAP" in rendered and "main" in rendered and "pkg.a" in rendered

            app.action_goto("metrics")
            await settle(pilot)
            assert app.check_action("import_todos", ()) is True
            app.action_import_todos()
            await app.workers.wait_for_complete()
            await settle(pilot)
            titles = [row["title"] for row in JournalStore(app.registry.db_path).list_tasks(app.active_project)]
            assert any("TODO: wire a" in title for title in titles)

            app.action_goto("journal")
            assert app.check_action("new_note_editor", ()) is True
            assert app.check_action("import_todos", ()) is False
            assert app.check_action("import_todos_any", ()) is True

    asyncio.run(exercise())


def test_standup_view_lists_projects_and_cycles_its_window(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "standup-project", commit=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.email", "t@e.com"],
                   check=True, capture_output=True, text=True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            JournalStore(app.registry.db_path).add_task(app.active_project, "Finish the dialog")
            assert app.check_action("standup", ()) is False  # footer shows it in the lobby
            assert app.check_action("standup_any", ()) is True  # but the key works here
            await pilot.press("u")
            assert app.current_view == "standup"
            assert app.query_one("#project-list").display is True
            text = app._standup_text().plain
            assert "last 24 hours" in text and "standup-project" in text and "Finish the dialog" in text
            await pilot.press("u")
            assert app._standup_days == 3 and "last 3 days" in app._standup_text().plain
            await pilot.press("escape")
            assert app.current_view == "home"
            assert app.check_action("standup", ()) is True

    asyncio.run(exercise())


def _register_with_origin(registry_module, repository: Path, url: str) -> None:
    subprocess.run(["git", "-C", str(repository), "remote", "add", "origin", url],
                   check=True, capture_output=True, text=True)
    registry_module.ProjectRegistry().register(repository)


def test_remove_project_asks_first_and_never_touches_files(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.registry as registry_module
    from breezy_trace.screens import ConfirmScreen

    _isolate(tmp_path, monkeypatch)
    keep = _init_repo(tmp_path / "keep-me")
    drop = _init_repo(tmp_path / "drop-me")
    registry = registry_module.ProjectRegistry()
    registry.register(keep)
    doomed = registry.register(drop)
    JournalStore(registry.db_path).add_note(doomed, "A note that will go")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._highlighted = doomed.id
            app.action_remove_project()
            await settle(pilot)
            assert isinstance(app.screen, ConfirmScreen)
            await pilot.press("escape")  # cancelling changes nothing
            await settle(pilot)
            assert len(app.registry.list_projects()) == 2

            app.action_remove_project()
            await settle(pilot)
            app.screen.dismiss(True)
            await settle(pilot)
            assert [p.name for p in app.registry.list_projects()] == ["keep-me"]
            assert app.query_one("#project-table").row_count == 1
            assert JournalStore(app.registry.db_path).totals()["notes"] == 0
            assert (drop / ".git").exists()  # the repository itself is untouched
            assert app.check_action("remove_project", ()) is True
            app._handle_project_pick(keep)
            await settle(pilot)
            assert app.check_action("remove_project", ()) is False  # lobby only

    asyncio.run(exercise())


def test_resume_shows_where_the_project_lives_and_w_opens_it(tmp_path: Path, monkeypatch) -> None:
    import breezy_trace.app as app_module
    import breezy_trace.registry as registry_module

    _isolate(tmp_path, monkeypatch)
    hosted = _init_repo(tmp_path / "hosted")
    local_only = _init_repo(tmp_path / "local-only")
    _register_with_origin(registry_module, hosted, "git@github.com:kiku/hosted.git")
    opened: list[str] = []
    monkeypatch.setattr(app_module.webbrowser, "open", lambda url: opened.append(url) or True)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(hosted)
            await settle(pilot)
            assert "GitHub · kiku/hosted" in app._parts["overview"][0].plain
            app.action_open_web()
            assert opened == ["https://github.com/kiku/hosted"]

            app._handle_project_pick(local_only)
            await settle(pilot)
            assert "Local only" in app._parts["overview"][0].plain
            app.action_open_web()
            assert opened == ["https://github.com/kiku/hosted"]  # nothing opened for a local-only repo

    asyncio.run(exercise())


def test_slow_git_never_blocks_the_interface(tmp_path: Path, monkeypatch) -> None:
    """Regression: a slow repository used to freeze every key until its Git calls finished."""
    import time

    import breezy_trace.app as app_module

    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "slow-project", commit=True)
    real = app_module.inspect_status

    def slow(path):
        time.sleep(2.0)  # far longer than the normal cost of registering a project
        return real(path)

    monkeypatch.setattr(app_module, "inspect_status", slow)

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            started = time.monotonic()
            app._handle_project_pick(repository)
            # Registering a project runs a few quick Git commands (slow on Windows), but the
            # page must not wait for the 2-second status call: that is the freeze we fixed.
            assert time.monotonic() - started < 1.2
            assert app.current_view == "overview"
            assert "Loading" in app._main.query_one("#content").render().plain
            await pilot.press("t")  # keys work while the page is still loading
            assert isinstance(app.screen, FormScreen)
            app.screen.dismiss(None)
            await settle(pilot)
            assert "slow-project" in app._parts["overview"][0].plain

    asyncio.run(exercise())


def test_project_keys_explain_themselves_in_the_lobby(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "hint-project")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            assert app.check_action("need_project", ("t",)) is True
            assert app.check_action("need_project", ("n",)) is False  # n = New project here
            assert app.check_action("new_project", ()) is True and app.check_action("clone_project", ()) is True
            await pilot.press("t")  # must not raise or open anything
            assert app.screen is app._main
            app._handle_project_pick(repository)
            await settle(pilot)
            assert app.check_action("need_project", ("t",)) is False
            assert app.check_action("new_project", ()) is False and app.check_action("clone_project", ()) is False

    asyncio.run(exercise())


def test_new_project_creates_registers_and_opens_it(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app.action_new_project()
            await settle(pilot)
            form = app.screen
            assert isinstance(form, FormScreen)
            form.query_one("#field-name", Input).value = "brand-new"
            form.query_one("#field-parent", Input).value = str(workspace)
            form._save()
            await settle(pilot)
            assert (workspace / "brand-new" / ".git").is_dir()
            assert app.active_project.name == "brand-new" and app.current_view == "overview"
            assert app.query_one("#project-table").row_count == 1
            assert [p.name for p in app.registry.list_projects()] == ["brand-new"]

    asyncio.run(exercise())


def test_clone_project_adds_the_clone_to_the_lobby(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    source = _init_repo(tmp_path / "source", commit=True)
    bare = tmp_path / "remote" / "cool-repo.git"
    bare.parent.mkdir()
    subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], check=True,
                   capture_output=True, text=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._start_clone({"url": str(bare), "parent": str(workspace)})
            await settle(pilot)
            assert (workspace / "cool-repo" / "app.py").exists()
            assert app.active_project.name == "cool-repo"
            assert app.query_one("#project-table").row_count == 1
            app._start_clone({"url": str(bare), "parent": str(workspace)})  # already there: reported, not crashed
            await settle(pilot)
            assert len(app.registry.list_projects()) == 1

    asyncio.run(exercise())


def test_open_in_offers_editor_folder_and_terminal(tmp_path: Path, monkeypatch) -> None:
    from breezy_trace import launchers
    from breezy_trace.screens import ChoiceScreen

    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "open-in-project")
    started: list[list[str]] = []
    monkeypatch.setattr(launchers, "_spawn", lambda command, cwd=None: started.append(command))
    monkeypatch.setattr(launchers, "editor_command", lambda *a, **k: ["/usr/bin/code"])

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            assert app.check_action("open_in", ()) is True  # shown on Resume
            app.action_goto("journal")
            assert app.check_action("open_in", ()) is False and app.check_action("open_in_any", ()) is True
            app.action_goto("overview")
            await settle(pilot)
            app.action_open_in()
            await settle(pilot)
            assert isinstance(app.screen, ChoiceScreen)
            app.screen.dismiss("editor")
            await settle(pilot)
            assert started and started[-1][0] == "/usr/bin/code" and started[-1][1] == str(repository.resolve())

    asyncio.run(exercise())


def test_run_lists_detected_commands_and_explains_when_there_are_none(tmp_path: Path, monkeypatch) -> None:
    from breezy_trace.runners import RunCommand
    from breezy_trace.screens import ChoiceScreen

    _isolate(tmp_path, monkeypatch)
    bare = _init_repo(tmp_path / "bare-project")
    testable = _init_repo(tmp_path / "testable-project")
    (testable / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(bare)
            await settle(pilot)
            app.action_run_command()
            await settle(pilot)
            assert app.screen is app._main  # nothing detected: explained, no dialog

            app._handle_project_pick(testable)
            await settle(pilot)
            assert "RUN HERE" in app._parts["overview"][2].plain and "pytest" in app._parts["overview"][2].plain
            app.action_run_command()
            await settle(pilot)
            assert isinstance(app.screen, ChoiceScreen)
            app.screen.dismiss(None)
            await settle(pilot)
            # a missing program is reported, never crashes the UI
            missing = RunCommand("x", ("definitely-missing-program-xyz",), "test")
            app._run_chosen(app.active_project, [missing], "0")
            await settle(pilot)
            assert app.screen is app._main

    asyncio.run(exercise())


def test_resume_lists_the_changed_files(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    repository = _init_repo(tmp_path / "changes-project", commit=True)
    (repository / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (repository / "brand new.txt").write_text("x", encoding="utf-8")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(repository)
            await settle(pilot)
            left = app._parts["overview"][1].plain
            assert "M  app.py" in left and "?  brand new.txt" in left

    asyncio.run(exercise())


def test_adding_a_plain_folder_offers_to_create_a_repository(tmp_path: Path, monkeypatch) -> None:
    from breezy_trace.screens import ConfirmScreen

    _isolate(tmp_path, monkeypatch)
    plain = tmp_path / "plain-folder"
    plain.mkdir()
    (plain / "notes.txt").write_text("mine", encoding="utf-8")

    async def exercise() -> None:
        async with TraceApp(intro=False).run_test(size=(120, 36)) as pilot:
            app = pilot.app
            app._handle_project_pick(plain)
            await settle(pilot)
            assert isinstance(app.screen, ConfirmScreen)
            app.screen.dismiss(False)  # declining changes nothing
            await settle(pilot)
            assert not (plain / ".git").exists() and app.registry.list_projects() == []

            app._handle_project_pick(plain)
            await settle(pilot)
            app.screen.dismiss(True)
            await settle(pilot)
            assert (plain / ".git").is_dir() and app.active_project.name == "plain-folder"
            assert (plain / "notes.txt").read_text(encoding="utf-8") == "mine"

    asyncio.run(exercise())
