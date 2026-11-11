"""Textual terminal workspace for Breezy Trace.

Two levels: the *lobby* (every project, shared metrics and attention) and a full-width
*project page* (Resume, Metrics, Journal, Git, Activity, Code, Settings) opened by
selecting a project. Git is only ever read. Every manual feature the CLI offers is also
a visible key here, and ``?`` / ``F1`` open help from anywhere. No background watcher or
network call exists; background threads only run one-shot, read-only Git work.
"""

import subprocess
import time
import webbrowser
from contextlib import closing, suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, DirectoryTree, Footer, Input, Static
from textual.widgets.data_table import CellDoesNotExist, RowDoesNotExist

from breezy_trace import actions, launchers
from breezy_trace.activity import FileActivityStore
from breezy_trace.agents import AgentSessionStore
from breezy_trace.config import data_dir, database_path
from breezy_trace.database import connect
from breezy_trace.depgraph import build_dependency_graph, is_test_path
from breezy_trace.editor import NOTE_TEMPLATE, edit_text, parse_note_text
from breezy_trace.git import (
    branch_intelligence,
    changed_files,
    commit_activity,
    commit_graph,
    hot_files,
    inspect_details,
    inspect_status,
    parse_graph_line,
    recent_commits,
)
from breezy_trace.intro import IntroScreen
from breezy_trace.journal import JournalStore
from breezy_trace.metrics import (
    WEEKDAY_NAMES,
    WEEKDAYS,
    RepoMetrics,
    SinceDigest,
    collect_repo_metrics,
    describe_age,
    describe_elapsed,
    lobby_metrics,
    parse_since,
    relative_days,
    since_digest,
    streaks,
)
from breezy_trace.models import GitStatus, Project
from breezy_trace.polyglot_index import LANGUAGE_EXTENSIONS
from breezy_trace.registry import ProjectError, ProjectRegistry
from breezy_trace.remotes import list_remotes, primary_remote
from breezy_trace.runners import detect_commands, resolve_executable
from breezy_trace.screens import ChoiceScreen, ConfirmScreen, FormScreen, HelpScreen
from breezy_trace.settings import load_settings, save_setting
from breezy_trace.standup import collect_standup, window_label
from breezy_trace.theme import (
    CATEGORY,
    DEFAULT_THEME,
    HEAT,
    PALETTE,
    apply_theme,
    attention_rank,
    attention_reasons,
    changed_count,
    css_variables,
    current_theme,
    is_light_theme,
    is_unavailable,
    needs_attention,
    next_theme,
    state_color,
    state_segments,
    theme_label,
)
from breezy_trace.visuals import (
    CHECK,
    bar,
    bucket_days,
    heat_level,
    rebucket,
    sparkline,
    stacked_cells,
)

THEME_CSS = """
Screen { background: $tr-bg; color: $tr-text; }
#topbar { height: 1; padding: 0 1; background: $tr-surface; color: $tr-text; }
#tabs { height: 1; padding: 0 1; background: $tr-bg; }
TabLabel { width: auto; height: 1; padding: 0 2 0 0; color: $tr-muted; }
TabLabel:hover { color: $tr-text; }
TabLabel.active { color: $tr-text; text-style: bold underline; }
#workspace { layout: horizontal; height: 1fr; padding: 0 1; }
#project-list {
    width: 42; min-width: 30; height: 1fr; margin-right: 1;
    border: round $tr-border; background: $tr-surface;
    border-title-color: $tr-muted; border-title-style: bold;
}
#project-list:focus-within { border: round $tr-border-focus; border-title-color: $tr-primary; }
#project-table { height: 1fr; border: none; padding: 0; background: $tr-surface; }
#project-table > .datatable--header { background: $tr-surface; color: $tr-faint; text-style: bold; }
#project-table > .datatable--cursor { background: $tr-raised; color: $tr-text; text-style: bold; }
#project-table > .datatable--hover { background: $tr-raised; }
#content-panel {
    width: 1fr; height: 1fr; padding: 0 1;
    border: round $tr-border; background: $tr-surface;
    border-title-color: $tr-muted; border-title-style: bold;
    scrollbar-size-vertical: 1; scrollbar-background: $tr-surface;
    scrollbar-color: $tr-border; scrollbar-color-hover: $tr-faint; scrollbar-color-active: $tr-primary;
}
#content-panel:focus { border: round $tr-border-focus; border-title-color: $tr-primary; }
#content { width: 100%; height: auto; color: $tr-text; }
App { background: $tr-bg; color: $tr-text; }
Footer { background: $tr-surface; color: $tr-text; }
Footer FooterKey { background: $tr-surface; }
Footer .footer-key--key, FooterKey .footer-key--key { color: $tr-primary; background: $tr-surface; text-style: bold; }
Footer .footer-key--description, FooterKey .footer-key--description { color: $tr-text; background: $tr-surface; }
"""

# (view id, tab label, short tab label for narrow terminals, panel title)
TABS: tuple[tuple[str, str, str, str], ...] = (
    ("home", "‹ Lobby", "‹ Lobby", "LOBBY"),
    ("overview", "Resume", "Resume", "RESUME"),
    ("metrics", "Metrics", "Stats", "METRICS"),
    ("journal", "Journal", "Note", "JOURNAL"),
    ("git", "Git", "Git", "GIT"),
    ("activity", "Activity", "Act", "ACTIVITY"),
    ("code", "Code", "Code", "CODE"),
    ("settings", "Settings", "Set", "SETTINGS"),
)
VIEW_TITLES = {view: title for view, _label, _short, title in TABS}
VIEW_TITLES["search"] = "SEARCH"
VIEW_TITLES["standup"] = "STANDUP"
LOBBY_VIEWS = ("home", "search", "standup")
ASYNC_VIEWS = frozenset({"overview", "git", "activity", "code"})
PROJECT_VIEWS = frozenset({"overview", "metrics", "journal", "git", "activity", "code", "settings"})
COLUMN_VIEWS = ("overview", "metrics")
PROJECT_ONLY_ACTIONS = frozenset(
    {"new_note", "new_task", "new_decision", "complete_task", "export_handoff", "open_web"}
)
# Keys that always work but are only *advertised* in the footer where they are relevant;
# a hidden "_any" twin keeps the key live everywhere else.
CONTEXT_KEYS: dict[str, frozenset[str]] = {
    "index_code": frozenset({"code"}),
    "scan_activity": frozenset({"activity"}),
    "sync_sessions": frozenset({"activity"}),
    "backup_data": frozenset({"home", "settings"}),
    "standup": frozenset({"home", "standup"}),
    "import_todos": frozenset({"metrics"}),
    "new_note_editor": frozenset({"journal"}),
    "open_in": frozenset({"overview"}),
    "run_command": frozenset({"overview"}),
}

# Keys that only make sense inside a project. Outside one they explain themselves
# instead of silently doing nothing.
PROJECT_KEY_HINTS: dict[str, str] = {
    "n": "add a note",
    "t": "add a task",
    "d": "record a decision",
    "x": "complete a task",
    "e": "export a handoff",
    "w": "open the project on the web",
    "i": "index its code",
    "a": "scan its activity",
    "s": "sync agent sessions",
    "m": "import its TODOs",
    "N": "write a note in your editor",
    "v": "open it in your editor, file manager or terminal",
    "R": "run its tests or build",
}
LOBBY_ONLY_ACTIONS = frozenset({"open_project", "remove_project", "new_project", "clone_project"})

NARROW_WIDTH = 80
WIDE_WIDTH = 100
HISTORY_DAYS = 84
LIST_WIDTH = 42
METRICS_TTL_SECONDS = 120
MUTED_PREFIXES = (
    "Run:",
    "CLI:",
    "Commands:",
    "Metadata only",
    "Capture context",
    "Local symbol",
    "Recorded Git",
    "Remote branch",
    "Scanning is",
    "Supported discovery",
    "Refresh metadata",
    "Create a portable",
    "Restore explicitly",
    "Inspect this",
    "Other editor",
    "Claude Code and OpenCode metadata",
    "Keys:",
    "Key:",
    "Press ?",
    "Theme:",
)


def _clean(value: str) -> str:
    """Drop control characters so stored text cannot disturb the terminal."""
    return "".join(ch for ch in value if ch.isprintable() or ch in "\n\t")


def _heading(out: Text, title: str, note: str = "") -> None:
    if out.plain:
        out.append("\n")
    out.append(title.upper(), style=f"bold {PALETTE['primary']}")
    if note:
        out.append(f"  {note}", style=PALETTE["muted"])
    out.append("\n")


def _kv(out: Text, label: str, value: str, color: str | None = None, width: int = 14) -> None:
    out.append(f"{label:<{width}}", style=PALETTE["muted"])
    out.append(f"{value}\n", style=color or PALETTE["text"])


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _segments_text(status: GitStatus) -> Text:
    text = Text()
    for index, (piece, color) in enumerate(state_segments(status)):
        if index:
            text.append(" ")
        text.append(piece, style=color)
    return text


def _colorize(body: str) -> Text:
    """Give plain section/line text the palette: headings, muted hints, body."""
    out = Text()
    for index, line in enumerate(body.split("\n")):
        if index:
            out.append("\n")
        stripped = line.strip()
        is_heading = (
            bool(stripped)
            and not line.startswith((" ", "•", "○"))
            and any(ch.isalpha() for ch in stripped)
            and stripped == stripped.upper()
        )
        if is_heading:
            out.append(_clean(line), style=f"bold {PALETTE['primary']}")
        elif stripped.startswith(MUTED_PREFIXES):
            out.append(_clean(line), style=PALETTE["muted"])
        else:
            out.append(_clean(line))
    return out


class TabLabel(Static):
    """One-row clickable tab; the keyboard (1-7, Esc) is the primary way to switch."""

    def __init__(self, view: str, label: str) -> None:
        super().__init__(label, id=f"tab-{view}", markup=False)
        self.target_view = view

    def on_click(self) -> None:
        self.app.action_goto(self.target_view)


class ProjectPicker(ModalScreen[Path | None]):
    """Terminal-native folder picker for opening a Git project."""

    CSS = """
    ProjectPicker { align: center middle; background: $tr-bg 80%; }
    #picker-dialog { width: 86%; height: 86%; border: round $tr-primary; background: $tr-surface; padding: 1 2; }
    #picker-title { color: $tr-primary; text-style: bold; height: auto; }
    #picker-hint { color: $tr-muted; height: auto; }
    #folder-path { margin: 1 0; }
    #directory-tree { height: 1fr; border: round $tr-border; background: $tr-surface; }
    #picker-actions { height: 3; align: right middle; }
    #picker-actions Button { margin-left: 1; }
    """
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Static("OPEN A PROJECT FOLDER", id="picker-title")
            yield Static(
                "Tip: drag a folder from Explorer into the box below, or paste its path.",
                id="picker-hint",
            )
            yield Input(
                value=str(Path.home()), placeholder="Enter any folder path", id="folder-path"
            )
            yield DirectoryTree(str(Path.home()), id="directory-tree")
            with Horizontal(id="picker-actions"):
                yield Button("Open path", id="open-path", variant="primary")
                yield Button("Use selected folder", id="open-selected")
                yield Button("Cancel", id="cancel-picker")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-picker":
            self.dismiss(None)
            return
        if event.button.id == "open-path":
            value = self.query_one("#folder-path", Input).value.strip()
            if value:
                self.dismiss(Path(actions.clean_path_text(value)).expanduser())
            return
        if event.button.id == "open-selected":
            node = self.query_one("#directory-tree", DirectoryTree).cursor_node
            if node is not None and node.data is not None:
                self.dismiss(Path(node.data.path))


class TraceApp(App[None]):
    """Lobby of all projects, plus a full-width page for the project you open."""

    TITLE = "Breezy Trace"
    SUB_TITLE = "by Breezy Labs"
    CSS = THEME_CSS
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help", key_display="?"),
        Binding("f1", "show_help", "Help", show=False, priority=True),
        Binding("o", "open_project", "Add repo"),
        Binding("n", "new_project", "New"),
        Binding("c", "clone_project", "Clone"),
        Binding("delete", "remove_project", "Remove"),
        Binding("w", "open_web", "Web"),
        Binding("v", "open_in", "Open in"),
        Binding("v", "open_in_any", "Open in", show=False),
        Binding("R", "run_command", "Run"),
        Binding("R", "run_command_any", "Run", show=False),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("u", "standup", "Standup"),
        Binding("u", "standup_any", "Standup", show=False),
        Binding("escape", "goto('home')", "Lobby"),
        Binding("n", "new_note", "Note"),
        Binding("t", "new_task", "Task"),
        Binding("d", "new_decision", "Decision"),
        Binding("x", "complete_task", "Done"),
        Binding("e", "export_handoff", "Export"),
        Binding("i", "index_code", "Index"),
        Binding("i", "index_code_any", "Index", show=False),
        Binding("a", "scan_activity", "Scan"),
        Binding("a", "scan_activity_any", "Scan", show=False),
        Binding("s", "sync_sessions", "Sessions"),
        Binding("s", "sync_sessions_any", "Sessions", show=False),
        Binding("b", "backup_data", "Backup"),
        Binding("b", "backup_data_any", "Backup", show=False),
        Binding("m", "import_todos", "TODOs"),
        Binding("m", "import_todos_any", "TODOs", show=False),
        Binding("N", "new_note_editor", "Editor note"),
        Binding("N", "new_note_editor_any", "Editor note", show=False),
        Binding("r", "refresh_view", "Refresh"),
        Binding("T", "cycle_theme", "Theme"),
        Binding("f2", "cycle_theme", "Theme", show=False),
        Binding("1", "goto('overview')", "Resume", show=False),
        Binding("2", "goto('metrics')", "Metrics", show=False),
        Binding("3", "goto('journal')", "Journal", show=False),
        Binding("4", "goto('git')", "Git", show=False),
        Binding("5", "goto('activity')", "Activity", show=False),
        Binding("6", "goto('code')", "Code", show=False),
        Binding("7", "goto('settings')", "Settings", show=False),
        *[Binding(key, f"need_project('{key}')", show=False) for key in PROJECT_KEY_HINTS],
    ]

    def __init__(
        self, project: Project | None = None, intro: bool = True, theme: str | None = None
    ) -> None:
        super().__init__()
        apply_theme(theme or load_settings().get("theme", DEFAULT_THEME))
        self.registry = ProjectRegistry()
        self.active_project = project
        self.current_view = "home"
        self.intro = intro
        self._main: Screen | None = None
        self._boot_ids: list[str] = []
        self._states: dict[str, GitStatus] = {}
        self._history: dict[str, list[int]] = {}
        self._parts: dict[str, tuple[Text, Text, Text]] = {}
        self._metrics: dict[str, tuple[float, RepoMetrics | None]] = {}
        self._metrics_pending: set[str] = set()
        self._since: dict[str, str | None] = {}
        self._last_search: tuple[str, list] = ("", [])
        self._standup_days = 1
        self._highlighted: str | None = None
        self._view_seq = 0
        self._overview_state: dict[str, tuple[GitStatus, list[int]]] = {}
        self._width = 120
        self._wide = False

    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        variables.update(css_variables())
        return variables

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield Static(id="topbar", markup=False)
        with Horizontal(id="tabs"):
            for view, label, _short, _title in TABS:
                yield TabLabel(view, label)
        with Container(id="workspace"):
            with Vertical(id="project-list"):
                yield DataTable(id="project-table", cursor_type="row")
            with VerticalScroll(id="content-panel"):
                yield Static(id="content", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        # The intro, dialogs and help are screens stacked on top of this one, and
        # App.query_one only searches the active screen, so keep a handle on the main
        # screen for every lookup. Background results can land while one of them is up.
        self._main = self.screen
        self._sync_builtin_theme()
        self._main.query_one("#project-list").border_title = "PROJECTS"
        table = self._main.query_one("#project-table", DataTable)
        table.add_column(" ", key="state", width=1)
        table.add_column("PROJECT", key="name", width=14)
        table.add_column("STATE", key="delta", width=7)
        table.add_column("30 DAYS", key="spark", width=10)
        self._width = self.size.width
        self._wide = self.size.width >= WIDE_WIDTH
        self._apply_responsive_layout(self.size.width)
        projects = self.registry.list_projects()
        self._boot_ids = [project.id for project in projects]
        for project in projects:
            self._add_project_row(project)
        if self.active_project:
            self._since[self.active_project.id] = self.active_project.last_opened_at
            self.registry.mark_opened(self.active_project.id)
            self._render_view("overview")
        else:
            self._render_view("home")
        self._start_state_load(projects)
        if self.intro:
            self.push_screen(IntroScreen())

    def on_resize(self, event) -> None:
        """Stack the lobby panels vertically on narrow terminals; re-flow column views."""
        if self._main is None:
            return
        self._width = event.size.width
        self._apply_responsive_layout(event.size.width)
        wide = event.size.width >= WIDE_WIDTH
        if wide != self._wide:
            self._wide = wide
            if self.current_view in self._parts:
                self._main.query_one("#content", Static).update(
                    self._columns_renderable(self.current_view)
                )

    def _apply_responsive_layout(self, width: int) -> None:
        assert self._main is not None
        narrow = width <= NARROW_WIDTH
        for label in self._main.query(TabLabel):
            short = next(s for view, _long, s, _t in TABS if view == label.target_view)
            long = next(lg for view, lg, _s, _t in TABS if view == label.target_view)
            label.update(short if narrow else long)
        workspace = self._main.query_one("#workspace", Container)
        project_list = self._main.query_one("#project-list", Vertical)
        content_panel = self._main.query_one("#content-panel", VerticalScroll)
        if narrow:
            workspace.styles.layout = "vertical"
            project_list.styles.width = "100%"
            project_list.styles.height = 9
            project_list.styles.min_height = 6
            project_list.styles.margin = (0, 0, 1, 0)
            content_panel.styles.min_height = 8
        else:
            workspace.styles.layout = "horizontal"
            project_list.styles.width = LIST_WIDTH
            project_list.styles.height = "1fr"
            project_list.styles.min_height = 0
            project_list.styles.margin = (0, 1, 0, 0)
            content_panel.styles.min_height = 0

    # ------------------------------------------------------- project list state

    def _add_project_row(self, project: Project) -> None:
        assert self._main is not None
        table = self._main.query_one("#project-table", DataTable)
        table.add_row(
            Text("○", style=PALETTE["faint"]),
            project.name,
            Text(""),
            Text(""),
            key=project.id,
        )

    def _start_state_load(self, projects: list[Project]) -> None:
        if not projects:
            return
        self.run_worker(
            lambda: self._load_states(projects),
            thread=True,
            group="project-states",
            exit_on_error=False,
        )

    def _load_states(self, projects: list[Project]) -> None:
        """Thread worker: read-only Git status and commit history, applied as each lands."""
        for project in projects:
            path = Path(project.path)
            try:
                status = inspect_status(path)
            except Exception:  # noqa: BLE001
                status = GitStatus.unavailable("Status unavailable.")
            try:
                daily = bucket_days(commit_activity(path, HISTORY_DAYS), HISTORY_DAYS, date.today())
            except Exception:  # noqa: BLE001
                daily = [0] * HISTORY_DAYS
            try:
                self.call_from_thread(self._apply_state, project.id, status, daily)
            except Exception:  # noqa: BLE001
                return  # the app is shutting down

    def _record_state(
        self, project_id: str, status: GitStatus, daily: list[int] | None = None
    ) -> None:
        assert self._main is not None
        self._states[project_id] = status
        if daily is not None:
            self._history[project_id] = daily
        table = self._main.query_one("#project-table", DataTable)
        try:
            table.update_cell(
                project_id, "state", Text("●", style=state_color(status)), update_width=False
            )
            table.update_cell(project_id, "delta", _segments_text(status), update_width=False)
            history = self._history.get(project_id)
            if history is not None:
                table.update_cell(
                    project_id,
                    "spark",
                    Text(sparkline(rebucket(history[-30:], 3)), style=PALETTE["primary"]),
                    update_width=False,
                )
        except (CellDoesNotExist, RowDoesNotExist):
            return

    def _apply_state(
        self, project_id: str, status: GitStatus, daily: list[int] | None = None
    ) -> None:
        self._record_state(project_id, status, daily)
        if self.current_view == "home":
            self._render_view("home")
        else:
            self._refresh_topbar()

    def boot_status(self) -> tuple[int, int, int, list[str | None]]:
        """For the intro: (projects, loaded, needing attention, per-project state colours)."""
        ids = self._boot_ids
        loaded = [item for item in ids if item in self._states]
        attention = sum(needs_attention(self._states[item]) for item in loaded)
        colors = [state_color(self._states[item]) if item in self._states else None for item in ids]
        return len(ids), len(loaded), attention, colors

    # ------------------------------------------------------------------ chrome

    def _refresh_topbar(self) -> None:
        assert self._main is not None
        bar_text = Text()
        bar_text.append("trace", style=f"bold {PALETTE['primary']}")
        project = self.active_project
        if self.current_view in LOBBY_VIEWS or project is None:
            bar_text.append("  ·  by Breezy Labs", style=PALETTE["muted"])
            total = len(self.registry.list_projects())
            if total:
                attention = sum(needs_attention(status) for status in self._states.values())
                bar_text.append(
                    f"   {total} project{'s' if total != 1 else ''}", style=PALETTE["text"]
                )
                if attention:
                    bar_text.append(f"  ·  {attention} need attention", style=PALETTE["dirty"])
        else:
            bar_text.append("  ›  ", style=PALETTE["faint"])
            bar_text.append(project.name, style=f"bold {PALETTE['text']}")
            status = self._states.get(project.id)
            if status is not None and not is_unavailable(status):
                bar_text.append(f"   {status.branch}  ", style=PALETTE["muted"])
                bar_text.append_text(_segments_text(status))
        bar_text.append("   ? help", style=PALETTE["faint"])
        self._main.query_one("#topbar", Static).update(bar_text)

    def _render(self, view: str, body: RenderableType) -> None:
        assert self._main is not None
        lobby = view in LOBBY_VIEWS
        self._view_seq += 1
        self.current_view = view
        self._main.query_one("#project-list").display = lobby
        self._main.query_one("#tabs").display = not lobby
        panel = self._main.query_one("#content-panel", VerticalScroll)
        panel.border_title = VIEW_TITLES.get(view, view.upper())
        self._main.query_one("#content", Static).update(
            _colorize(body) if isinstance(body, str) else body
        )
        for label in self._main.query(TabLabel):
            label.set_class(label.target_view == view, "active")
        self._refresh_topbar()
        panel.scroll_home(animate=False)
        if self.screen is self._main:
            if lobby:
                self._main.query_one("#project-table", DataTable).focus()
            else:
                panel.focus()

    # ------------------------------------------------------------------- theme

    def _sync_builtin_theme(self) -> None:
        """Match Textual's own light/dark base so built-in widgets stay readable."""
        light = is_light_theme()
        if hasattr(App, "theme"):
            with suppress(Exception):  # an unknown theme name on an older Textual
                self.theme = "textual-light" if light else "textual-dark"
        elif hasattr(App, "dark"):
            with suppress(Exception):
                self.dark = not light

    def action_cycle_theme(self) -> None:
        if self.screen is not self._main:
            return
        name = apply_theme(next_theme(current_theme()))
        save_setting("theme", name)
        self._sync_builtin_theme()
        with suppress(Exception):  # restyling is cosmetic; never fail the key press
            self.refresh_css()
        for project_id, status in list(self._states.items()):
            self._record_state(project_id, status)
        self._render_view(self.current_view)
        self.notify(theme_label(name), title="Theme")

    # ------------------------------------------------------------- interaction

    def _handle_project_pick(self, selected_path: Path | None) -> None:
        if selected_path is None:
            return
        try:
            project = self.registry.find_by_path(selected_path)
            if project is None:
                project = self.registry.register(selected_path)
                self._boot_ids.append(project.id)
                self._add_project_row(project)
                self._start_state_load([project])
        except (OSError, ProjectError, ValueError) as error:
            if (
                isinstance(error, ProjectError)
                and str(error).startswith("Not inside a Git repository")
                and selected_path.is_dir()
            ):
                self._offer_git_init(selected_path)
                return
            self.notify(str(error), title="Could not open project", severity="error")
            return
        self.active_project = project
        self._since[project.id] = project.last_opened_at
        self.registry.mark_opened(project.id)
        self._render_view("overview")

    def _offer_git_init(self, folder: Path) -> None:
        self.push_screen(
            ConfirmScreen(
                "NOT A GIT REPOSITORY",
                [
                    str(folder),
                    "",
                    "Breezy Trace works with Git repositories.",
                    "Create an empty Git repository in this folder and add it?",
                    "Your existing files are not changed.",
                ],
                "Create repository",
            ),
            lambda confirmed: self._init_folder(folder, bool(confirmed)),
        )

    def _init_folder(self, folder: Path, confirmed: bool) -> None:
        if not confirmed:
            return
        try:
            project = actions.adopt_folder(self.registry, folder)
        except (ProjectError, OSError) as error:
            self.notify(str(error), title="Could not add the folder", severity="error")
            return
        self._adopt_project(project)
        self.notify(f'Added "{project.name}" to Breezy Trace.')

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            self._highlighted = str(event.row_key.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        project_id = str(event.row_key.value)
        self.active_project = next(
            (item for item in self.registry.list_projects() if item.id == project_id),
            None,
        )
        if self.active_project:
            self._since[self.active_project.id] = self.active_project.last_opened_at
            self.registry.mark_opened(self.active_project.id)
            self._render_view("overview")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Show only the keys that make sense here: project choice and adding repos are
        lobby actions; project actions and the way back appear inside a project."""
        if action in LOBBY_ONLY_ACTIONS:
            return self.current_view == "home"
        if action == "need_project":
            key = parameters[0] if parameters else ""
            if self.current_view in PROJECT_VIEWS:
                return False
            return not (key == "n" and self.current_view == "home")  # n = new project here
        if action == "goto" and parameters == ("home",):
            return self.current_view != "home"
        if action in PROJECT_ONLY_ACTIONS:
            return self.current_view in PROJECT_VIEWS
        if action in CONTEXT_KEYS:
            return self.current_view in CONTEXT_KEYS[action]
        if action.endswith("_any") and action[:-4] in CONTEXT_KEYS:
            base = action[:-4]
            if base in ("backup_data", "standup"):
                return self.current_view not in CONTEXT_KEYS[base]
            return (
                self.current_view in PROJECT_VIEWS and self.current_view not in CONTEXT_KEYS[base]
            )
        return True

    def action_goto(self, view: str) -> None:
        if self.screen is not self._main:
            return
        if view != "home" and self.active_project is None:
            self.notify(
                "Select a project in the lobby and press Enter.",
                title="No project open",
            )
            return
        self._render_view(view)

    def action_open_project(self) -> None:
        if self.screen is not self._main:
            return
        self.push_screen(ProjectPicker(), self._handle_project_pick)

    def action_show_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.screen.dismiss(None)
            return
        if isinstance(self.screen, IntroScreen):
            return
        self.push_screen(HelpScreen())

    def action_refresh_view(self) -> None:
        if self.screen is not self._main:
            return
        if self.current_view == "home":
            self._start_state_load(self.registry.list_projects())
        elif self.current_view == "metrics" and self.active_project is not None:
            self._metrics.pop(self.active_project.id, None)
        self._render_view(self.current_view)
        self.notify("Refreshed.")

    # --------------------------------------------------------- manual features

    def _project_for_action(self) -> Project | None:
        if self.screen is not self._main or self.current_view == "home":
            return None
        return self.active_project

    def _journal_call(self, message: str, operation) -> None:
        try:
            operation(JournalStore(self.registry.db_path))
        except (ValueError, RuntimeError) as error:
            self.notify(str(error), title="Not saved", severity="error")
            return
        self.notify(message)
        self._render_view(self.current_view)

    def action_new_note(self) -> None:
        project = self._project_for_action()
        if project is None:
            return
        self.push_screen(
            FormScreen(
                "NEW NOTE",
                [
                    ("title", "Title", "What happened, or what comes next?"),
                    ("body", "Details (optional)", ""),
                ],
                hint="Saved to this project's journal. Nothing is inferred.",
            ),
            lambda values: self._save_note(project, values),
        )

    def _save_note(self, project: Project, values: dict[str, str] | None) -> None:
        if values:
            self._journal_call(
                "Note saved.",
                lambda store: store.add_note(project, values["title"], values.get("body", "")),
            )

    def action_new_task(self) -> None:
        project = self._project_for_action()
        if project is None:
            return
        self.push_screen(
            FormScreen(
                "NEW TASK",
                [("title", "Task", "What needs doing?"), ("details", "Details (optional)", "")],
            ),
            lambda values: self._save_task(project, values),
        )

    def _save_task(self, project: Project, values: dict[str, str] | None) -> None:
        if values:
            self._journal_call(
                "Task added.",
                lambda store: store.add_task(project, values["title"], values.get("details", "")),
            )

    def action_new_decision(self) -> None:
        project = self._project_for_action()
        if project is None:
            return
        self.push_screen(
            FormScreen(
                "RECORD A DECISION",
                [
                    ("title", "Topic", "What was decided about?"),
                    ("decision", "Decision", "What did you decide?"),
                    ("context", "Why (optional)", ""),
                ],
                hint="Decisions are shown on Resume so you remember the reasoning later.",
                required=("title", "decision"),
            ),
            lambda values: self._save_decision(project, values),
        )

    def _save_decision(self, project: Project, values: dict[str, str] | None) -> None:
        if not values:
            return
        self._journal_call(
            "Decision recorded.",
            lambda store: store.add_decision(
                project, values["title"], values["decision"], values.get("context", "")
            ),
        )

    def action_complete_task(self) -> None:
        project = self._project_for_action()
        if project is None:
            return
        open_tasks = JournalStore(self.registry.db_path).list_tasks(project, "open")
        if not open_tasks:
            self.notify("This project has no open tasks.")
            return
        self.push_screen(
            ChoiceScreen(
                "COMPLETE A TASK", [(row["id"], _clean(row["title"])) for row in open_tasks]
            ),
            lambda task_id: self._complete_task(project, task_id),
        )

    def _complete_task(self, project: Project, task_id: str | None) -> None:
        if task_id:
            self._journal_call(
                "Task completed.", lambda store: store.complete_task(project, task_id)
            )

    def _start_job(self, label: str, work) -> None:
        self.notify(f"{label}…", title="Working")
        self.run_worker(
            lambda: self._run_job(label, work),
            thread=True,
            group="jobs",
            exit_on_error=False,
        )

    def _run_job(self, label: str, work) -> None:
        try:
            message, failed = work(), False
        except Exception as error:  # noqa: BLE001
            message, failed = str(error) or error.__class__.__name__, True
        try:
            self.call_from_thread(self._job_done, label, message, failed)
        except Exception:  # noqa: BLE001
            return

    def _job_done(self, label: str, message: str, failed: bool) -> None:
        self.notify(
            message,
            title=f"{label} failed" if failed else label,
            severity="error" if failed else "information",
            timeout=8,
        )
        if self.screen is self._main and self.current_view != "home":
            self._render_view(self.current_view)

    def action_index_code(self) -> None:
        project = self._project_for_action()
        if project is not None:
            self._start_job(
                "Indexing code", lambda: actions.index_code(self.registry.db_path, project)
            )

    def action_scan_activity(self) -> None:
        project = self._project_for_action()
        if project is not None:
            self._start_job(
                "Scanning activity", lambda: actions.scan_activity(self.registry.db_path, project)
            )

    def action_sync_sessions(self) -> None:
        project = self._project_for_action()
        if project is not None:
            self._start_job(
                "Syncing sessions", lambda: actions.sync_sessions(self.registry.db_path, project)
            )

    def action_backup_data(self) -> None:
        if self.screen is not self._main:
            return
        self._start_job(
            "Backing up",
            lambda: f"Backup created: {actions.backup_now(self.registry.db_path, data_dir())}",
        )

    def action_export_handoff(self) -> None:
        project = self._project_for_action()
        if project is not None:
            self._start_job(
                "Writing handoff",
                lambda: (
                    "Handoff written: "
                    + str(
                        actions.export_handoff(
                            self.registry.db_path, project, data_dir() / "handoffs"
                        )
                    )
                ),
            )

    def action_import_todos(self) -> None:
        project = self._project_for_action()
        if project is not None:
            self._start_job(
                "Importing TODOs", lambda: actions.import_todos(self.registry.db_path, project)
            )

    def action_new_note_editor(self) -> None:
        """Write a note in $VISUAL / $EDITOR; the terminal UI pauses while it is open."""
        project = self._project_for_action()
        if project is None:
            return
        try:
            with self.suspend():
                text = edit_text(NOTE_TEMPLATE)
        except Exception as error:  # noqa: BLE001
            self.notify(str(error), title="Could not open an editor", severity="error")
            return
        title, body = parse_note_text(text)
        if not title:
            self.notify("Nothing written; note cancelled.")
            return
        self._journal_call("Note saved.", lambda store: store.add_note(project, title, body))

    def action_import_todos_any(self) -> None:
        self.action_import_todos()

    def action_new_note_editor_any(self) -> None:
        self.action_new_note_editor()

    def action_index_code_any(self) -> None:
        self.action_index_code()

    def action_scan_activity_any(self) -> None:
        self.action_scan_activity()

    def action_sync_sessions_any(self) -> None:
        self.action_sync_sessions()

    def action_backup_data_any(self) -> None:
        self.action_backup_data()

    # ---------------------------------- projects: add, create, clone, remove, web

    def action_need_project(self, key: str) -> None:
        if self.screen is not self._main:
            return
        self.notify(
            f"Highlight a project and press Enter first. Then {key} will "
            f"{PROJECT_KEY_HINTS.get(key, 'work')}.",
            title="Not inside a project",
        )

    def _adopt_project(self, project: Project) -> None:
        """Show a just-registered project in the list and open it."""
        self._boot_ids.append(project.id)
        self._add_project_row(project)
        self._start_state_load([project])
        self.active_project = project
        self._since[project.id] = project.last_opened_at
        self.registry.mark_opened(project.id)
        self._render_view("overview")

    def action_new_project(self) -> None:
        if self.screen is not self._main or self.current_view != "home":
            return
        self.push_screen(
            FormScreen(
                "NEW PROJECT",
                [
                    ("name", "Project name", "my-new-tool"),
                    ("parent", "Create it inside this folder", ""),
                ],
                hint="Makes a folder with an empty Git repository and adds it to Trace.",
                required=("name", "parent"),
                defaults={"parent": str(Path.cwd())},
            ),
            self._create_project,
        )

    def _create_project(self, values: dict[str, str] | None) -> None:
        if not values:
            return
        try:
            project = actions.create_project(
                self.registry, Path(actions.clean_path_text(values["parent"])), values["name"]
            )
        except (ProjectError, OSError) as error:
            self.notify(str(error), title="Could not create the project", severity="error")
            return
        self._adopt_project(project)
        self.notify(f'Created "{project.name}" and added it to Breezy Trace.')

    def action_clone_project(self) -> None:
        if self.screen is not self._main or self.current_view != "home":
            return
        self.push_screen(
            FormScreen(
                "CLONE A REPOSITORY",
                [
                    (
                        "url",
                        "Repository URL",
                        "https://github.com/owner/repo.git  or  git@gitlab.com:group/repo.git",
                    ),
                    ("parent", "Clone it inside this folder", ""),
                ],
                hint="Runs git clone, which uses the network because you asked. Credentials stay with Git.",
                required=("url", "parent"),
                defaults={"parent": str(Path.cwd())},
            ),
            self._start_clone,
        )

    def _start_clone(self, values: dict[str, str] | None) -> None:
        if not values:
            return
        self.notify("Cloning; this can take a while.", title="Clone started")
        url, parent = values["url"], Path(actions.clean_path_text(values["parent"]))
        self.run_worker(
            lambda: self._run_clone(url, parent), thread=True, group="clone", exit_on_error=False
        )

    def _run_clone(self, url: str, parent: Path) -> None:
        try:
            project, message = actions.clone_project(self.registry, url, parent), ""
        except (ProjectError, OSError) as error:
            project, message = None, str(error)
        try:
            self.call_from_thread(self._clone_done, project, message)
        except Exception:  # noqa: BLE001
            return

    def _clone_done(self, project: Project | None, message: str) -> None:
        if project is None:
            self.notify(message, title="Clone failed", severity="error", timeout=10)
            return
        if self.screen is self._main:
            self._adopt_project(project)
        self.notify(f'Cloned "{project.name}" and added it to Breezy Trace.')

    def _highlighted_project(self) -> Project | None:
        wanted = self._highlighted or (self._boot_ids[0] if self._boot_ids else None)
        return next((item for item in self.registry.list_projects() if item.id == wanted), None)

    def action_remove_project(self) -> None:
        """Forget a project in Trace. Its files and Git history are never touched."""
        if self.screen is not self._main or self.current_view != "home":
            return
        project = self._highlighted_project()
        if project is None:
            self.notify("Highlight a project in the list first.", title="Nothing to remove")
            return
        counts = JournalStore(self.registry.db_path).project_counts(project)
        recorded = (
            counts["notes"] + counts["open_tasks"] + counts["done_tasks"] + counts["decisions"]
        )
        lines = [
            f"{project.name}",
            f"{project.path}",
            "",
            "This removes the project from Breezy Trace and deletes what Trace recorded for it:",
            (
                f"  {counts['notes']} notes · {counts['open_tasks'] + counts['done_tasks']} tasks · "
                f"{counts['decisions']} decisions, plus its code index and activity."
            ),
            "",
            "Your files and Git history on disk are NOT touched.",
        ]
        if recorded:
            lines.append("Tip: cancel and press b to back up the database first.")
        self.push_screen(
            ConfirmScreen("REMOVE FROM BREEZY TRACE?", lines, "Remove from Trace"),
            lambda confirmed: self._remove_project(project, bool(confirmed)),
        )

    def _remove_project(self, project: Project, confirmed: bool) -> None:
        assert self._main is not None
        if not confirmed:
            return
        if not self.registry.unregister(project.path):
            self.notify("That project was already gone.", severity="warning")
        with suppress(RowDoesNotExist):
            self._main.query_one("#project-table", DataTable).remove_row(project.id)
        self._states.pop(project.id, None)
        self._history.pop(project.id, None)
        self._metrics.pop(project.id, None)
        self._since.pop(project.id, None)
        self._boot_ids = [item for item in self._boot_ids if item != project.id]
        self._highlighted = None
        if self.active_project is not None and self.active_project.id == project.id:
            self.active_project = None
        self._render_view("home")
        self.notify(f'Removed "{project.name}" from Breezy Trace. Your files are untouched.')

    def action_open_web(self) -> None:
        """Open the project's GitHub / GitLab / ... page in your browser."""
        project = self._project_for_action()
        if project is None:
            return
        remote = primary_remote(list_remotes(Path(project.path)))
        if remote is None:
            self.notify(
                "This project has no Git remote, so it only exists on this machine.",
                title="Local only",
            )
            return
        webbrowser.open(remote.web_url)
        self.notify(f"{remote.host}/{remote.slug}", title="Opened in your browser")

    # --------------------------------------------- developer actions: open, run

    def action_open_in(self) -> None:
        """Open the project in your editor, file manager or terminal."""
        project = self._project_for_action()
        if project is None:
            return
        path = Path(project.path)
        options: list[tuple[str, str]] = []
        editor = launchers.editor_command()
        if editor:
            options.append(("editor", f"Editor  ({Path(editor[0]).stem})"))
        options.append(("folder", launchers.file_manager_name()))
        options.append(("terminal", "Terminal here"))
        remote = primary_remote(list_remotes(path))
        if remote is not None:
            options.append(("web", f"{remote.provider}: {remote.slug}  (browser)"))
        self.push_screen(
            ChoiceScreen("OPEN THIS PROJECT IN…", options),
            lambda choice: self._open_in(project, choice),
        )

    def _open_in(self, project: Project, choice: str | None) -> None:
        if choice is None:
            return
        if choice == "web":
            self.action_open_web()
            return
        try:
            message = launchers.open_target(choice, Path(project.path))
        except launchers.LaunchError as error:
            self.notify(str(error), title="Could not open", severity="error", timeout=10)
            return
        self.notify(message)

    def action_run_command(self) -> None:
        """Run one of the project's own commands (tests, build, lint, scripts)."""
        project = self._project_for_action()
        if project is None:
            return
        commands = detect_commands(Path(project.path))
        if not commands:
            self.notify(
                "Looked for pytest, npm scripts, cargo, go, gradle, make and dotnet files "
                "in the project folder.",
                title="Nothing to run here",
            )
            return
        self.push_screen(
            ChoiceScreen(
                f"RUN IN {project.name.upper()}",
                [
                    (str(index), f"{item.label:<20} {item.source}")
                    for index, item in enumerate(commands)
                ],
            ),
            lambda choice: self._run_chosen(project, commands, choice),
        )

    def _run_chosen(self, project: Project, commands: list, choice: str | None) -> None:
        if choice is None:
            return
        command = commands[int(choice)]
        argv = resolve_executable(command)
        if argv is None:
            self.notify(
                f"{command.args[0]} was not found on your PATH.",
                title="Cannot run",
                severity="error",
            )
            return
        started = time.monotonic()
        code = -1
        try:
            with self.suspend():
                print(f"\n$ {command.display}\n  in {project.path}\n")
                code = subprocess.run(argv, cwd=project.path, check=False).returncode
                seconds = time.monotonic() - started
                print(
                    f"\n{'Passed' if code == 0 else 'Failed'}: exit code {code} after {seconds:.1f}s"
                )
                input("Press Enter to return to Breezy Trace... ")
        except Exception as error:  # noqa: BLE001  suspending is not supported everywhere
            self.notify(str(error), title="Could not run the command", severity="error")
            return
        self.notify(
            f"{command.label}: exit code {code}",
            title="Finished",
            severity="information" if code == 0 else "error",
        )
        self._render_view(self.current_view)

    def action_open_in_any(self) -> None:
        self.action_open_in()

    def action_run_command_any(self) -> None:
        self.action_run_command()

    # ----------------------------------------------------------------- standup

    def action_standup(self) -> None:
        """Your commits, finished tasks and what is next, across every project."""
        if self.screen is not self._main:
            return
        windows = (1, 3, 7)
        if self.current_view == "standup":
            self._standup_days = windows[(windows.index(self._standup_days) + 1) % len(windows)]
        else:
            self._standup_days = 1
        self._render_async("standup", self._standup_text)

    def action_standup_any(self) -> None:
        self.action_standup()

    def _standup_text(self) -> Text:
        days = self._standup_days
        since = datetime.now(UTC) - timedelta(days=days)
        report = collect_standup(self.registry.db_path, self.registry.list_projects(), since)
        out = Text()
        out.append(f"Standup · {window_label(days)}", style=f"bold {PALETTE['text']}")
        out.append("   u cycles 1 / 3 / 7 days · Esc lobby\n", style=PALETTE["faint"])
        if not any(item.has_activity for item in report):
            out.append("\nNothing recorded in this window.\n", style=PALETTE["muted"])
        for item in report:
            if out.plain:
                out.append("\n")
            out.append(item.name, style=f"bold {PALETTE['primary']}")
            out.append("\n")
            for sha, _day, subject in item.commits:
                out.append(f"{'commit':<9}", style=f"bold {PALETTE['primary']}")
                out.append(f"{sha} ", style=PALETTE["faint"])
                out.append(f"{_clean(subject)[:70]}\n")
            for title in item.done:
                out.append(f"{'done':<9}", style=f"bold {PALETTE['clean']}")
                out.append(f"{_clean(title)[:80]}\n")
            for title, decision in item.decisions:
                out.append(f"{'decided':<9}", style=f"bold {PALETTE['decision']}")
                out.append(f"{_clean(title)}: {_clean(decision)[:60]}\n")
            for title in item.notes:
                out.append(f"{'note':<9}", style=f"bold {PALETTE['muted']}")
                out.append(f"{_clean(title)[:80]}\n")
            for title in item.next_up:
                out.append(f"{'next':<9}", style=f"bold {PALETTE['dirty']}")
                out.append(f"{_clean(title)[:80]}\n")
        out.append(
            "\nbreezy-trace standup  prints this as Markdown (add --days N)\n",
            style=PALETTE["faint"],
        )
        return out

    # ------------------------------------------------------------------ search

    def action_search(self) -> None:
        if self.screen is not self._main:
            return
        self.push_screen(
            FormScreen(
                "SEARCH EVERYTHING",
                [("query", "Search for", "text in any note, task or decision")],
                hint="Searches every project's journal, on this machine only.",
            ),
            self._run_search,
        )

    def _run_search(self, values: dict[str, str] | None) -> None:
        if not values:
            return
        query = values["query"]
        rows = JournalStore(self.registry.db_path).search_all(query, limit=40)
        self._last_search = (query, rows)
        self._render("search", self._search_text())

    def _search_text(self) -> Text:
        query, rows = self._last_search
        out = Text()
        if not query:
            out.append("Press / to search every note, task and decision.\n", style=PALETTE["muted"])
            return out
        out.append(f"{len(rows)} result{'s' if len(rows) != 1 else ''} for ", style="bold")
        out.append(f'"{_clean(query)}"\n', style=f"bold {PALETTE['primary']}")
        if not rows:
            out.append(
                "\nNo matches in any project's notes, tasks or decisions.\n", style=PALETTE["muted"]
            )
        for row in rows:
            kind = row["kind"]
            if kind == "task":
                color = PALETTE["clean"] if row["status"] == "done" else PALETTE["dirty"]
                label = "task done" if row["status"] == "done" else "task"
            elif kind == "decision":
                color, label = PALETTE["decision"], "decision"
            else:
                color, label = PALETTE["primary"], "note"
            out.append("\n")
            out.append(f"{label:<10}", style=f"bold {color}")
            out.append(f"{_clean(row['project_name'])[:16]:<17}", style=PALETTE["muted"])
            out.append(_clean(row["title"]), style=f"bold {PALETTE['text']}")
            out.append(f"  {row['created_at'][:10]}\n", style=PALETTE["faint"])
            detail = " ".join(_clean(row["detail"] or "").split())
            if detail:
                out.append(f"{'':<27}{detail[:90]}\n", style=PALETTE["muted"])
        out.append("\nEsc returns to the lobby · / searches again\n", style=PALETTE["faint"])
        return out

    # ------------------------------------------------------ view building blocks

    def _append_digest(self, out: Text, digest: SinceDigest) -> None:
        ago = describe_elapsed(datetime.now(UTC) - digest.since)
        _heading(out, "Since you last opened", ago)
        if digest.total_commits == 0:
            out.append("No new commits.\n", style=PALETTE["muted"])
            return
        plural = "s" if digest.total_commits != 1 else ""
        authors = "s" if digest.authors != 1 else ""
        out.append(
            f"{digest.total_commits} commit{plural} by {digest.authors} author{authors}",
            style=f"bold {PALETTE['text']}",
        )
        out.append(f"  +{digest.added}", style=PALETTE["clean"])
        out.append(f" -{digest.deleted}", style=PALETTE["danger"])
        out.append(f"  in {digest.files} files\n", style=PALETTE["muted"])
        for sha, author, subject in digest.commits[:4]:
            out.append(f"{sha} ", style=PALETTE["primary"])
            out.append(_clean(subject)[:56])
            out.append(f"  {_clean(author)}\n", style=PALETTE["faint"])
        if digest.total_commits > 4:
            out.append(f"+{digest.total_commits - 4} more\n", style=PALETTE["muted"])

    def _append_graph(self, out: Text, path: Path) -> None:
        lines = commit_graph(path, limit=28)
        _heading(out, "Branch graph", "local branches, cached remotes, HEAD")
        if not lines:
            out.append("No commits to draw.\n", style=PALETTE["muted"])
            return
        lanes = (
            PALETTE["primary"],
            PALETTE["decision"],
            PALETTE["clean"],
            PALETTE["dirty"],
            PALETTE["danger"],
        )
        for line in lines:
            graph, sha, refs, subject = parse_graph_line(line)
            for index, char in enumerate(graph):
                if char == "*":
                    out.append(char, style=f"bold {PALETTE['primary']}")
                elif char in "|/\\_-.":
                    out.append(char, style=lanes[(index // 2) % len(lanes)])
                else:
                    out.append(char)
            if not sha:
                out.append("\n")
                continue
            out.append(f"{sha} ", style=PALETTE["faint"])
            if refs:
                out.append("(", style=PALETTE["muted"])
                for position, ref in enumerate(refs):
                    if position:
                        out.append(", ", style=PALETTE["muted"])
                    if ref.startswith("tag:"):
                        style = PALETTE["dirty"]
                    elif "/" in ref and not ref.startswith("HEAD"):
                        style = PALETTE["decision"]
                    else:
                        style = f"bold {PALETTE['clean']}"
                    out.append(_clean(ref), style=style)
                out.append(") ", style=PALETTE["muted"])
            out.append(_clean(subject)[:70] + "\n")

    def _append_dependency_map(self, out: Text, project: Project) -> None:
        """Python import graph from the index: entry-point trees, hubs and cycles."""
        with closing(connect(self.registry.db_path)) as connection, connection:
            files = [
                row["path"]
                for row in connection.execute(
                    "SELECT path FROM code_indexed_files WHERE project_id = ? AND path LIKE '%.py'",
                    (project.id,),
                )
            ]
            imports = [
                (row["path"], row["module"])
                for row in connection.execute(
                    "SELECT path, module FROM code_imports WHERE project_id = ? AND path LIKE '%.py'",
                    (project.id,),
                )
            ]
        graph = build_dependency_graph(files, imports)
        if not graph.nodes:
            return
        cycles = graph.cycles()
        _heading(out, "Dependency map", "Python modules importing each other")
        out.append(
            f"{len(graph.nodes)} modules · {graph.edge_count} links · ", style=PALETTE["muted"]
        )
        out.append(
            f"{len(cycles)} import cycle{'s' if len(cycles) != 1 else ''}\n",
            style=PALETTE["danger"] if cycles else PALETTE["clean"],
        )
        entries = graph.entry_points()
        entries = [path for path in entries if not is_test_path(path)] or entries
        for root in entries[:2]:
            out.append("\n")
            for prefix, name, note in graph.tree(root, max_depth=3, max_children=5):
                out.append(prefix, style=PALETTE["muted"])
                if not prefix:
                    out.append(name, style=f"bold {PALETTE['primary']}")
                elif note == "cycle":
                    out.append(name, style=PALETTE["danger"])
                    out.append("  (cycle)", style=PALETTE["danger"])
                elif note == "more":
                    out.append(name, style=PALETTE["muted"])
                else:
                    out.append(name)
                out.append("\n")
        incoming = graph.fan_in()
        hubs = incoming.most_common(6)
        if hubs:
            _heading(out, "Most depended on", "imported by this many modules")
            for path, count in hubs:
                name = graph.names[path]
                shown = name if len(name) <= 30 else "…" + name[-29:]
                out.append(f"{shown:<30} ", style=PALETTE["text"])
                out.append(bar(count, hubs[0][1], 12), style=PALETTE["primary"])
                out.append(f" {count}\n", style=PALETTE["muted"])
        for cycle in cycles[:3]:
            _heading(out, "Import cycle")
            out.append(" -> ".join([*cycle, cycle[0]]) + "\n", style=PALETTE["danger"])

    def _append_code_stats(self, out: Text, project: Project) -> None:
        with closing(connect(self.registry.db_path)) as connection, connection:
            imports = connection.execute(
                "SELECT module, COUNT(*) AS n FROM code_imports WHERE project_id = ? "
                "GROUP BY module ORDER BY n DESC, module LIMIT 8",
                (project.id,),
            ).fetchall()
            heavy = connection.execute(
                "SELECT path, COUNT(*) AS n FROM code_symbols WHERE project_id = ? "
                "GROUP BY path ORDER BY n DESC, path LIMIT 8",
                (project.id,),
            ).fetchall()
        for title, rows, note in (
            ("Most imported modules", imports, "how often each is imported"),
            ("Files with most symbols", heavy, "functions, classes, methods"),
        ):
            if not rows:
                continue
            _heading(out, title, note)
            peak = rows[0]["n"]
            for row in rows:
                name = _clean(str(row[0]))
                shown = name if len(name) <= 30 else "…" + name[-29:]
                out.append(f"{shown:<30} ", style=PALETTE["text"])
                out.append(bar(row["n"], peak, 12), style=PALETTE["primary"])
                out.append(f" {row['n']}\n", style=PALETTE["muted"])

    # ------------------------------------------------------------------- views

    def _render_view(self, view: str) -> None:
        if view == "search":
            self._render("search", self._search_text())
            return
        if view == "home":
            self._render("home", self._home())
            return
        project = self.active_project
        if project is None:
            self._render("home", self._home())
            return
        if view == "standup":
            self._render_async("standup", self._standup_text)
        elif view in ASYNC_VIEWS:
            builders = {
                "overview": self._overview,
                "git": self._git,
                "activity": self._activity_view,
                "code": self._code,
            }
            self._render_async(view, lambda: builders[view](project))
        else:
            renderers = {
                "metrics": self._metrics_view,
                "journal": self._journal,
                "settings": self._settings,
            }
            renderer = renderers.get(view)
            self._render(view, renderer(project) if renderer else "Unknown workspace view.")

    def _render_async(self, view: str, build) -> None:
        """Switch to ``view`` immediately and fill it in from a background thread, so a
        slow repository (thousands of changed files, a network drive) can never freeze
        the keyboard. Results for a view you have already left are dropped."""
        self._render(view, Text("Loading…", style=PALETTE["muted"]))
        ticket = self._view_seq
        self.run_worker(
            lambda: self._build_view(ticket, view, build),
            thread=True,
            group="views",
            exclusive=True,
            exit_on_error=False,
        )

    def _build_view(self, ticket: int, view: str, build) -> None:
        try:
            body = build()
        except Exception as error:  # noqa: BLE001
            body = Text(f"Could not load this view: {error}", style=PALETTE["danger"])
        try:
            self.call_from_thread(self._finish_view, ticket, view, body)
        except Exception:  # noqa: BLE001
            return  # the app is shutting down

    def _finish_view(self, ticket: int, view: str, body: RenderableType) -> None:
        if self._main is None or ticket != self._view_seq or self.current_view != view:
            return
        project = self.active_project
        if view == "overview" and project is not None:
            state = self._overview_state.pop(project.id, None)
            if state is not None:
                self._record_state(project.id, state[0], state[1])
        self._main.query_one("#content", Static).update(
            _colorize(body) if isinstance(body, str) else body
        )
        self._refresh_topbar()

    def _columns_renderable(self, view: str) -> RenderableType:
        """Two columns on wide terminals, one stacked column otherwise."""
        header, left, right = self._parts[view]
        if self._width < WIDE_WIDTH:
            stacked = Text()
            stacked.append_text(header)
            stacked.append_text(left)
            stacked.append("\n")
            stacked.append_text(right)
            return stacked
        grid = Table.grid(expand=True, padding=(0, 3))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(left, right)
        return Group(header, grid)

    def _home(self) -> Text:
        projects = self.registry.list_projects()
        out = Text()
        if not projects:
            out.append("Welcome to Breezy Trace\n", style=f"bold {PALETTE['text']}")
            out.append(
                "Project memory for the terminal: notes, tasks, decisions and Git state,\n"
                "kept per project and stored only on this machine.\n",
                style=PALETTE["muted"],
            )
            _heading(out, "Get started")
            for key, meaning in (
                ("o", "add a repository that already exists on this machine"),
                ("n", "create a brand-new project (folder + empty Git repository)"),
                ("c", "clone a project from GitHub, GitLab or any Git URL"),
            ):
                out.append(f"{key}   ", style=f"bold {PALETTE['primary']}")
                out.append(f"{meaning}\n")
            out.append("breezy-trace register .", style=f"bold {PALETTE['primary']}")
            out.append("   or register the repository you are standing in, from your shell\n")
            out.append("?", style=f"bold {PALETTE['primary']}")
            out.append("   help: every key and manual feature\n")
            return out

        loaded = [(item, self._states[item.id]) for item in projects if item.id in self._states]
        attention = sorted(
            ((item, status) for item, status in loaded if needs_attention(status)),
            key=lambda pair: (attention_rank(pair[1]), pair[0].name.lower()),
        )
        out.append(f"{len(projects)} project{'s' if len(projects) != 1 else ''}", style="bold")
        if len(loaded) < len(projects):
            out.append("  ·  checking Git state…", style=PALETTE["muted"])
        elif attention:
            out.append(f"  ·  {len(attention)} need attention", style=PALETTE["dirty"])
        else:
            out.append("  ·  all clean", style=PALETTE["clean"])
        out.append("\n")

        names = {item.id: item.name for item in projects}
        overall = lobby_metrics(
            {pid: days for pid, days in self._history.items() if pid in names},
            names,
            date.today(),
        )
        store = JournalStore(self.registry.db_path)
        if overall is not None:
            _heading(out, "Metrics", "all projects")
            out.append(f"{'Commits 7d':<14}", style=PALETTE["muted"])
            out.append(f"{overall.commits_7d}", style=f"bold {PALETTE['text']}")
            if overall.trend is not None:
                arrow, color = (
                    ("↑", PALETTE["clean"])
                    if overall.trend > 0
                    else ("↓", PALETTE["dirty"])
                    if overall.trend < 0
                    else ("→", PALETTE["muted"])
                )
                out.append(f"  {arrow} {abs(overall.trend) * 100:.0f}% vs previous 7d", style=color)
            out.append("\n")
            _kv(out, "Commits 30d", f"{overall.commits_30d}")
            out.append(f"{'30 days':<14}", style=PALETTE["muted"])
            out.append(sparkline(overall.daily_total[-30:]) + "\n", style=PALETTE["primary"])
            _kv(
                out,
                "Active",
                f"{overall.active_projects} of {overall.tracked_projects} projects this week",
            )
            _kv(
                out,
                "Streak",
                f"{overall.streak} day{'s' if overall.streak != 1 else ''} (any project)",
            )
            if overall.best_weekday is not None:
                _kv(out, "Busiest day", WEEKDAY_NAMES[overall.best_weekday])
            if overall.stalest is not None and overall.stalest[1] >= 7:
                quiet = overall.stalest[1]
                shown = f"{quiet} days" if quiet < HISTORY_DAYS else f"{HISTORY_DAYS}+ days"
                _kv(out, "Quietest", f"{overall.stalest[0]} · {shown}")
            if loaded:
                dirty = sum(changed_count(s) > 0 for _p, s in loaded)
                behind = sum(s.behind > 0 for _p, s in loaded)
                unpushed = sum(s.ahead > 0 for _p, s in loaded)
                clean = sum(not needs_attention(s) and not is_unavailable(s) for _p, s in loaded)
                _kv(
                    out,
                    "Git state",
                    f"{dirty} dirty · {unpushed} unpushed · {behind} behind · {clean} clean",
                )
            totals = store.totals()
            _kv(
                out,
                "Journal",
                f"{totals['notes']} notes · {totals['open_tasks']} open tasks · "
                f"{totals['done_tasks']} done · {totals['decisions']} decisions",
            )

        if attention:
            _heading(out, "Needs attention")
            for item, status in attention:
                out.append("● ", style=state_color(status))
                out.append(item.name, style=f"bold {PALETTE['text']}")
                out.append(f"   on {status.branch}", style=PALETTE["muted"])
                out.append(f"   {' · '.join(attention_reasons(status))}\n", style=PALETTE["muted"])

        open_total = store.count_open_tasks()
        if open_total:
            _heading(out, f"Open tasks ({open_total})", "across all projects")
            for row in store.recent_open_tasks(limit=6):
                out.append("○ ", style=PALETTE["dirty"])
                out.append(_clean(row["title"]))
                out.append(f"   {_clean(row['project_name'])}\n", style=PALETTE["muted"])

        ranked = [(item, self._history[item.id]) for item in projects if item.id in self._history]
        if ranked:
            weekly = {item.id: rebucket(days, 7) for item, days in ranked}
            peak = max((max(values) for values in weekly.values() if values), default=0)
            ranked.sort(key=lambda pair: (-sum(pair[1][-28:]), pair[0].name.lower()))
            _heading(out, "Activity", "12 weeks · commits per week")
            for item, days in ranked:
                name = item.name if len(item.name) <= 14 else item.name[:13] + "…"
                out.append(f"{name:<14} ", style=PALETTE["text"])
                for value in weekly[item.id]:
                    out.append("■ ", style=HEAT[heat_level(value, peak)])
                out.append(f" {sum(days)}\n", style=PALETTE["muted"])
            out.append("less ", style=PALETTE["faint"])
            for level in range(len(HEAT)):
                out.append("■ ", style=HEAT[level])
            out.append("more\n", style=PALETTE["faint"])
        out.append(
            f"\nState: ± changed files · ↑ unpushed commits · ↓ behind upstream · {CHECK} clean\n",
            style=PALETTE["faint"],
        )
        out.append(
            "Enter open · o add existing repo · n new project · c clone from URL · "
            "Delete remove · ? help\n",
            style=PALETTE["faint"],
        )
        return out

    def _overview(self, project: Project) -> RenderableType:
        path = Path(project.path)
        status = inspect_status(path)
        daily = bucket_days(commit_activity(path, HISTORY_DAYS), HISTORY_DAYS, date.today())
        self._overview_state[project.id] = (status, daily)
        details = inspect_details(path)
        commits = recent_commits(path, limit=8)
        store = JournalStore(self.registry.db_path)
        notes = store.list_entries(project, limit=1)
        open_tasks = [row for row in store.list_tasks(project) if row["status"] == "open"]
        decisions = store.list_decisions(project, limit=1)

        header = Text()
        header.append(project.name, style=f"bold {PALETTE['text']}")
        header.append(f"\n{project.path}\n", style=PALETTE["faint"])
        remote = primary_remote(list_remotes(path))
        if remote is not None:
            header.append(remote.label, style=f"bold {PALETTE['primary']}")
            header.append("   press w to open it\n", style=PALETTE["faint"])
        else:
            header.append("Local only · no Git remote\n", style=PALETTE["muted"])

        out = Text()
        since = parse_since(self._since.get(project.id))
        digest = since_digest(path, since) if since is not None else None
        if digest is not None:
            self._append_digest(out, digest)
        _heading(out, "Working tree")
        if is_unavailable(status):
            out.append(f"{status.summary}\n", style=PALETTE["danger"])
        else:
            out.append(status.branch, style=f"bold {PALETTE['text']}")
            out.append("  ")
            out.append_text(_segments_text(status))
            out.append(
                f"\n{status.staged} staged · {status.modified} modified · "
                f"{status.untracked} untracked\n",
                style=PALETTE["muted"],
            )
            if not details.get("available", True):
                out.append(
                    "Git details unavailable (command failed or timed out)\n",
                    style=PALETTE["muted"],
                )
            else:
                if details["conflicts"]:
                    out.append(
                        f"{details['conflicts']} merge conflicts\n",
                        style=f"bold {PALETTE['danger']}",
                    )
                if details["stashes"]:
                    out.append(f"{details['stashes']} stashes\n", style=PALETTE["muted"])
        if not is_unavailable(status):
            total_changed, changes = changed_files(path, limit=8)
            letter_colors = {
                "A": PALETTE["clean"],
                "M": PALETTE["dirty"],
                "D": PALETTE["danger"],
                "R": PALETTE["primary"],
                "U": PALETTE["danger"],
                "?": PALETTE["faint"],
            }
            for letter, name in changes:
                out.append(
                    f"{letter}  ", style=f"bold {letter_colors.get(letter, PALETTE['text'])}"
                )
                shown = name if len(name) <= 46 else "…" + name[-45:]
                out.append(f"{_clean(shown)}\n")
            if total_changed > len(changes):
                out.append(f"+{total_changed - len(changes)} more files\n", style=PALETTE["muted"])
        recent = daily[-30:]
        streak, best = streaks(daily)
        out.append("Commits 30d  ", style=PALETTE["muted"])
        out.append(sparkline(recent), style=PALETTE["primary"])
        out.append(f"  {sum(recent)}\n", style=PALETTE["muted"])
        out.append(
            f"7d {sum(daily[-7:])} · streak {streak}d (best {best}d) · more on the Metrics tab (2)\n",
            style=PALETTE["muted"],
        )

        _heading(out, "Last note")
        if notes:
            note = notes[0]
            out.append(_clean(note["title"]), style=f"bold {PALETTE['text']}")
            out.append(f"  {note['created_at'][:10]}\n", style=PALETTE["faint"])
            body = _clean(note["body"]).strip()
            if body:
                snippet = " ".join(body.split())
                out.append(
                    (snippet[:200] + "…" if len(snippet) > 200 else snippet) + "\n",
                    style=PALETTE["muted"],
                )
        else:
            out.append("None yet · press n to write one\n", style=PALETTE["muted"])

        _heading(out, f"Open tasks ({len(open_tasks)})")
        for row in open_tasks[:6]:
            out.append("○ ", style=PALETTE["dirty"])
            out.append(_clean(row["title"]) + "\n")
        if len(open_tasks) > 6:
            out.append(f"+{len(open_tasks) - 6} more\n", style=PALETTE["muted"])
        if not open_tasks:
            out.append("No open tasks · press t to add one\n", style=PALETTE["muted"])
        else:
            out.append("t add · x complete\n", style=PALETTE["faint"])

        _heading(out, "Latest decision")
        if decisions:
            decision = decisions[0]
            out.append(_clean(decision["title"]), style=f"bold {PALETTE['decision']}")
            out.append(f"  {_clean(decision['decision'])}\n")
        else:
            out.append("None yet · press d to record one\n", style=PALETTE["muted"])

        side = Text()
        _heading(side, "Recent commits")
        for item in commits:
            side.append(f"{item['sha']}  ", style=PALETTE["primary"])
            side.append(f"{item['date']}  ", style=PALETTE["faint"])
            side.append(f"{item['subject']}\n")
        if not commits:
            side.append("No local commits found.\n", style=PALETTE["muted"])

        hot = hot_files(path, days=30, limit=6)
        _heading(side, "Hot files", "most changed · 30 days")
        if hot:
            peak = hot[0][1]
            for name, count in hot:
                shown = name if len(name) <= 26 else "…" + name[-25:]
                side.append(f"{shown:<26} ", style=PALETTE["text"])
                side.append(bar(count, peak, 10), style=PALETTE["primary"])
                side.append(f" {count}\n", style=PALETTE["muted"])
        else:
            side.append("No changes in the last 30 days.\n", style=PALETTE["muted"])

        runnable = detect_commands(path)
        if runnable:
            _heading(side, "Run here", "press R to run one")
            for item in runnable[:6]:
                side.append(f"{item.label:<20}", style=PALETTE["text"])
                side.append(f"{item.source}\n", style=PALETTE["faint"])
            if len(runnable) > 6:
                side.append(f"+{len(runnable) - 6} more\n", style=PALETTE["muted"])

        out.rstrip()
        side.rstrip()
        self._parts["overview"] = (header, out, side)
        return self._columns_renderable("overview")

    # --------------------------------------------------------------- metrics tab

    def _metrics_view(self, project: Project) -> RenderableType:
        entry = self._metrics.get(project.id)
        fresh = entry is not None and time.monotonic() - entry[0] < METRICS_TTL_SECONDS
        if not fresh and project.id not in self._metrics_pending:
            self._metrics_pending.add(project.id)
            self.run_worker(
                lambda: self._load_metrics(project),
                thread=True,
                group="metrics",
                exit_on_error=False,
            )
        if entry is None:
            return Text("Computing metrics from Git history…", style=PALETTE["muted"])
        if entry[1] is None:
            return Text(
                "Metrics unavailable: this is not a Git repository, or Git could not run.",
                style=PALETTE["danger"],
            )
        return self._metrics_renderable(project, entry[1])

    def _load_metrics(self, project: Project) -> None:
        try:
            data = collect_repo_metrics(Path(project.path))
        except Exception:  # noqa: BLE001
            data = None
        try:
            self.call_from_thread(self._apply_metrics, project, data)
        except Exception:  # noqa: BLE001
            return

    def _apply_metrics(self, project: Project, data: RepoMetrics | None) -> None:
        self._metrics[project.id] = (time.monotonic(), data)
        self._metrics_pending.discard(project.id)
        if (
            self.current_view == "metrics"
            and self.active_project is not None
            and self.active_project.id == project.id
        ):
            self._render_view("metrics")

    def _metrics_renderable(self, project: Project, m: RepoMetrics) -> RenderableType:
        today = date.today()
        header = Text()
        header.append(project.name, style=f"bold {PALETTE['text']}")
        header.append("  metrics from local Git history · r to recompute\n", style=PALETTE["faint"])

        left = Text()
        _heading(left, "Overview")
        if m.first_commit is not None:
            _kv(
                left,
                "Age",
                f"{describe_age(m.first_commit, today)}  (since {m.first_commit.isoformat()})",
            )
        _kv(left, "Commits", f"{m.total_commits:,} total")
        if m.last_commit is not None:
            _kv(left, "Last commit", relative_days((today - m.last_commit.date()).days))
        _kv(left, "Tracked files", f"{m.tracked_files:,}  ·  {_human_bytes(m.tracked_bytes)}")
        _kv(left, "Refs", f"{m.heads} branches · {m.remotes} remote · {m.tags} tags")
        _kv(left, "Contributors", f"{m.contributors} in the last {HISTORY_DAYS} days")

        _heading(left, "Velocity")
        _kv(left, "7 days", f"{m.commits_7d} commits", PALETTE["primary"])
        _kv(left, "30 days", f"{m.commits_30d} commits")
        _kv(left, "84 days", f"{m.commits_84d} commits")
        _kv(left, "Active days", f"{m.active_days_30} of the last 30")
        _kv(
            left,
            "Streak",
            f"{m.streak_current} day{'s' if m.streak_current != 1 else ''} now · best {m.streak_longest}",
        )
        if m.active_days_30:
            _kv(left, "Pace", f"{m.commits_30d / m.active_days_30:.1f} commits per active day")
        left.append(f"{'12 weeks':<14}", style=PALETTE["muted"])
        left.append(sparkline(m.weekly), style=PALETTE["primary"])
        recent4, before4 = sum(m.weekly[-4:]), sum(m.weekly[-8:-4])
        if before4:
            change = (recent4 - before4) / before4 * 100
            arrow, color = (
                ("↑", PALETTE["clean"])
                if change > 0
                else ("↓", PALETTE["dirty"])
                if change < 0
                else ("→", PALETTE["muted"])
            )
            left.append(f"  {arrow} {abs(change):.0f}% vs prior 4 weeks", style=color)
        left.append("\n")

        _heading(left, "Churn", "last 30 days")
        _kv(left, "Added", f"+{m.lines_added:,} lines", PALETTE["clean"])
        _kv(left, "Removed", f"-{m.lines_deleted:,} lines", PALETTE["danger"])
        _kv(left, "Net", f"{m.lines_added - m.lines_deleted:+,} lines")
        _kv(left, "Files touched", f"{m.files_touched:,}")
        if m.commits_30d:
            _kv(
                left,
                "Per commit",
                f"{(m.lines_added + m.lines_deleted) / m.commits_30d:.0f} lines changed",
            )

        right = Text()
        _heading(right, "Rhythm", "when commits happen")
        peak_day = max(m.weekday) if m.weekday else 0
        for index, name in enumerate(WEEKDAYS):
            right.append(f"{name}  ", style=PALETTE["muted"])
            right.append(bar(m.weekday[index], peak_day, 16), style=PALETTE["primary"])
            right.append(f" {m.weekday[index]}\n", style=PALETTE["muted"])
        right.append("Hours  ", style=PALETTE["muted"])
        right.append(sparkline(m.hours) + "\n", style=PALETTE["primary"])
        labels = [" "] * 24
        for hour in (0, 6, 12, 18):
            labels[hour : hour + 2] = list(f"{hour:02d}")
        right.append("       " + "".join(labels) + "\n", style=PALETTE["faint"])
        if any(m.hours):
            busiest = max(range(24), key=m.hours.__getitem__)
            best_day = WEEKDAY_NAMES[max(range(7), key=m.weekday.__getitem__)]
            right.append(f"Peak: {best_day}s, around {busiest:02d}:00\n", style=PALETTE["muted"])

        _heading(right, "Contributors", f"last {HISTORY_DAYS} days")
        if m.authors:
            top = m.authors[0][1]
            for name, count in m.authors:
                shown = name if len(name) <= 18 else name[:17] + "…"
                right.append(f"{_clean(shown):<18} ", style=PALETTE["text"])
                right.append(bar(count, top, 10), style=PALETTE["primary"])
                right.append(f" {count}\n", style=PALETTE["muted"])
        else:
            right.append("No commits in this window.\n", style=PALETTE["muted"])

        _heading(right, "Languages", "by tracked file size")
        if m.languages:
            shown_langs = m.languages[:6]
            rest = sum(size for _name, size in m.languages[6:])
            items = shown_langs + ([("Other", rest)] if rest else [])
            total = sum(size for _name, size in items) or 1
            cells = stacked_cells([size for _name, size in items], 36)
            for index, count in enumerate(cells):
                right.append("█" * count, style=CATEGORY[index % len(CATEGORY)])
            right.append("\n")
            for index, (name, size) in enumerate(items):
                right.append("● ", style=CATEGORY[index % len(CATEGORY)])
                right.append(f"{name:<12}", style=PALETTE["text"])
                right.append(f"{size / total * 100:5.1f}%  ", style=PALETTE["muted"])
                right.append(f"{_human_bytes(size)}\n", style=PALETTE["faint"])
        else:
            right.append("No recognised source files.\n", style=PALETTE["muted"])

        _heading(right, "Hot files", "most changed · 30 days")
        if m.hot:
            top = m.hot[0][1]
            for name, count in m.hot:
                shown = name if len(name) <= 26 else "…" + name[-25:]
                right.append(f"{shown:<26} ", style=PALETTE["text"])
                right.append(bar(count, top, 10), style=PALETTE["primary"])
                right.append(f" {count}\n", style=PALETTE["muted"])
        else:
            right.append("No changes in the last 30 days.\n", style=PALETTE["muted"])

        _heading(right, "TODO / FIXME", f"{m.todo_total} in tracked files")
        if m.todos:
            for name, line, text in m.todos:
                shown = name if len(name) <= 22 else "…" + name[-21:]
                right.append(f"{shown}:{line}  ", style=PALETTE["primary"])
                right.append(f"{_clean(text)[:48]}\n", style=PALETTE["text"])
            if m.todo_total > len(m.todos):
                right.append(
                    f"+{m.todo_total - len(m.todos)} more (git grep -n TODO)\n",
                    style=PALETTE["muted"],
                )
        else:
            right.append("None found.\n", style=PALETTE["muted"])
        if m.todo_total:
            right.append(
                "\nPress m to turn these into tasks (never duplicates).\n", style=PALETTE["faint"]
            )

        left.rstrip()
        right.rstrip()
        self._parts["metrics"] = (header, left, right)
        return self._columns_renderable("metrics")

    def _journal(self, project: Project) -> str:
        store = JournalStore(self.registry.db_path)
        notes = store.list_entries(project, limit=12)
        tasks = store.list_tasks(project)
        decisions = store.list_decisions(project, limit=8)
        lines = [
            "PROJECT JOURNAL",
            "Capture context explicitly with the CLI. Nothing here is inferred.",
            "",
            f"NOTES ({len(notes)})",
        ]
        lines.extend(f"• {row['title']}  [{row['created_at'][:10]}]" for row in notes)
        if not notes:
            lines.append('No notes recorded. Try: breezy-trace note "Next session" --body "..."')
        lines.extend(["", f"OPEN TASKS ({sum(row['status'] == 'open' for row in tasks)})"])
        lines.extend(f"○ {row['title']}" for row in tasks if row["status"] == "open")
        if not any(row["status"] == "open" for row in tasks):
            lines.append("No open tasks.")
        lines.extend(["", "RECENT DECISIONS"])
        lines.extend(f"• {row['title']}: {row['decision']}" for row in decisions)
        if not decisions:
            lines.append("No decisions recorded.")
        lines.extend(
            [
                "",
                "Keys: n new note · N write a note in your editor · t new task · d record decision · x complete a task",
                "CLI: note TITLE · task TITLE · tasks [--all] · done TASK_ID",
                "CLI: decision TITLE DECISION · journal · resume",
            ]
        )
        return "\n".join(lines)

    def _agents(self, project: Project) -> str:
        sessions = AgentSessionStore(self.registry.db_path).list_sessions(project, limit=20)
        lines = [
            "AGENT SESSIONS",
            "Metadata only. Breezy Trace does not read prompts or transcripts.",
            "",
        ]
        for item in sessions:
            when = item["ended_at"] or item["started_at"] or "time unavailable"
            lines.append(f"{item['provider']}  ·  {when}")
            lines.append(f"  Session: {item['external_id']}")
            metadata = item["metadata"]
            if metadata:
                lines.append(f"  Metadata: {metadata}")
        if not sessions:
            lines.append("No sessions indexed yet.")
            lines.append("Run: breezy-trace sessions --sync")
        return "\n".join(lines)

    def _git(self, project: Project) -> RenderableType:
        data = branch_intelligence(Path(project.path))
        status = inspect_status(Path(project.path))
        if not data.get("available", True):
            return "GIT INTELLIGENCE · READ ONLY\n\nGit is unavailable or the inspection timed out."
        lines = [
            "GIT INTELLIGENCE · READ ONLY",
            f"Current branch: {status.branch}",
            f"Upstream: {data['upstream'] or 'not configured'}",
            (
                f"Ahead: {data['ahead'] if data['ahead'] is not None else 'unknown'} | "
                f"Behind: {data['behind'] if data['behind'] is not None else 'unknown'}"
            ),
            "Remote branch data is cached locally; no fetch is performed.",
            "",
            f"LOCAL BRANCHES ({len(data['local_branches'])})",
        ]
        lines.extend(f"• {item['name']}  {item['sha']}" for item in data["local_branches"])
        lines.extend(["", f"CACHED REMOTE BRANCHES ({len(data['remote_branches'])})"])
        lines.extend(f"• {item['name']}  {item['sha']}" for item in data["remote_branches"])
        lines.extend(["", f"UNPUSHED COMMITS ({len(data['unpushed_commits'])})"])
        lines.extend(f"• {item['sha']}  {item['subject']}" for item in data["unpushed_commits"])
        lines.extend(["", f"UPSTREAM-ONLY COMMITS ({len(data['upstream_only_commits'])})"])
        lines.extend(
            f"• {item['sha']}  {item['subject']}" for item in data["upstream_only_commits"]
        )
        lines.extend(["", f"STASHES ({len(data['stashes'])})"])
        lines.extend(f"• {item['ref']}  {item['subject']}" for item in data["stashes"])
        text = _colorize("\n".join(lines))
        text.append("\n")
        self._append_graph(text, Path(project.path))
        return text

    def _activity(self, project: Project) -> str:
        events = FileActivityStore(self.registry.db_path).list_events(project, limit=40)
        lines = [
            "FILE ACTIVITY",
            "Recorded Git path/status transitions only. File contents are never stored.",
            "",
        ]
        for item in events:
            lines.append(f"{item['observed_at'][:19]}  {item['event_type']}")
            lines.append(f"  {item['path']}")
            lines.append(f"  Evidence: {item['evidence']}")
        if not events:
            lines.extend(["No activity snapshots recorded.", "Run: breezy-trace activity scan"])
        lines.extend(
            [
                "",
                "Keys: a scan the working tree now · s sync agent sessions",
                "Scanning is explicit; no background watcher is running.",
            ]
        )
        return "\n".join(lines)

    def _activity_view(self, project: Project) -> str:
        """File activity and agent sessions share one screen."""
        return self._activity(project) + "\n\n" + self._agents(project)

    def _code(self, project: Project) -> RenderableType:
        with closing(connect(self.registry.db_path)) as connection, connection:
            files = connection.execute(
                "SELECT language, COUNT(*) AS count FROM code_indexed_files "
                "WHERE project_id = ? GROUP BY language ORDER BY language",
                (project.id,),
            ).fetchall()
            symbols = connection.execute(
                "SELECT language, COUNT(*) AS count FROM code_symbols "
                "WHERE project_id = ? GROUP BY language ORDER BY language",
                (project.id,),
            ).fetchall()
            imports = connection.execute(
                "SELECT language, COUNT(*) AS count FROM code_imports "
                "WHERE project_id = ? GROUP BY language ORDER BY language",
                (project.id,),
            ).fetchall()
        lines = [
            "CODE INTELLIGENCE",
            "Local symbol/import index. Source text is not persisted.",
            "",
            "INDEXED FILES",
        ]
        lines.extend(f"• {row['language']}: {row['count']}" for row in files)
        if not files:
            lines.append("No files indexed yet. Run: breezy-trace code index")
        lines.extend(["", "SYMBOLS"])
        lines.extend(f"• {row['language']}: {row['count']}" for row in symbols)
        if not symbols:
            lines.append("No symbols indexed.")
        lines.extend(["", "IMPORT RECORDS"])
        lines.extend(f"• {row['language']}: {row['count']}" for row in imports)
        if not imports:
            lines.append("No imports indexed.")
        lines.extend(["", "PARSER SUPPORT"])
        lines.extend(f"• {language}" for language in ["python", *sorted(LANGUAGE_EXTENSIONS)])
        lines.extend(
            [
                "",
                "Key: i  index symbols and imports now",
                "",
                "COMMANDS",
                "breezy-trace code index",
                "breezy-trace code languages",
                "breezy-trace code search QUERY",
                "breezy-trace code imports [QUERY]",
                "breezy-trace code calls [QUERY]",
            ]
        )
        text = _colorize("\n".join(lines))
        text.append("\n")
        self._append_code_stats(text, project)
        self._append_dependency_map(text, project)
        return text

    def _settings(self, project: Project) -> str:
        return "\n".join(
            [
                "PROJECT SETTINGS",
                "",
                f"Active project: {project.name}",
                f"Project path: {project.path}",
                f"Database: {database_path()}",
                "",
                "APPEARANCE",
                f"Theme: {theme_label(current_theme())}  (press T or F2 to switch)",
                "",
                "BACKUP & RESTORE",
                "Key: b  back up the database now",
                "Create a portable backup: breezy-trace backup",
                "Restore explicitly: breezy-trace restore FILE --yes",
                "Inspect this project: breezy-trace status · inspect · branches · resume",
                "",
                "INTEGRATIONS",
                "Claude Code and OpenCode metadata discovery are available.",
                "Other editor integrations are not yet implemented.",
                "",
                "HELP",
                "Press ? or F1 anywhere for every key and every manual feature.",
            ]
        )
