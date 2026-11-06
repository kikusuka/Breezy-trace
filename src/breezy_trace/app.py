"""Textual terminal interface for Breezy Trace."""

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from breezy_trace.git import branch_intelligence, inspect_status
from breezy_trace.journal import JournalStore
from breezy_trace.models import Project
from breezy_trace.registry import ProjectRegistry

THEME_CSS = """
Screen {
    layers: base overlay;
    background: #0F172A;
    color: #E2E8F0;
}
#hero {
    height: auto;
    padding: 1 2;
    margin: 1 1 0 1;
    border: round #334155;
    background: #111F35;
}
#brand {
    color: #BAE6FD;
    text-style: bold;
}
#subtitle {
    color: #94A3B8;
}
#workspace {
    height: 1fr;
    margin: 1 1 0 1;
}
#project-table {
    height: 1fr;
    border: round #334155;
}
#side-panel {
    width: 34;
    min-width: 28;
    border: round #334155;
    padding: 1 2;
    margin-left: 1;
}
.section-title {
    color: #38BDF8;
    text-style: bold;
    margin-bottom: 1;
}
#footer-note {
    height: auto;
    padding: 0 2 1 2;
    color: #94A3B8;
}
#intro {
    layer: overlay;
    width: 100%;
    height: 100%;
    align: center middle;
    background: #0F172A;
    opacity: 1;
}
#intro-copy {
    width: 100%;
    height: auto;
    content-align: center middle;
    text-align: center;
    color: #BAE6FD;
    text-style: bold;
}
#intro-kicker {
    width: 100%;
    height: auto;
    content-align: center middle;
    text-align: center;
    color: #38BDF8;
}
"""


class TraceApp(App[None]):
    """Global project dashboard and project overview."""

    TITLE = "Breezy Trace"
    SUB_TITLE = "by Breezy Labs"
    CSS = THEME_CSS
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+p", "focus_projects", "Projects"),
        Binding("ctrl+h", "home", "Home"),
        Binding("space", "skip_intro", "Skip intro", show=False),
        Binding("escape", "home", "Back"),
    ]

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.registry = ProjectRegistry()
        self.active_project = project

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="hero"):
            yield Static("BREEZY TRACE", id="brand")
            yield Static(
                "A clear trail through your projects, code, and development history.",
                id="subtitle",
            )
        with Horizontal(id="workspace"):
            with Vertical():
                yield Static("REGISTERED PROJECTS", classes="section-title")
                yield DataTable(id="project-table", cursor_type="row")
            with Vertical(id="side-panel"):
                yield Static("WORKSPACE", classes="section-title")
                yield Static(id="project-detail")
                yield Static("SHORTCUTS", classes="section-title")
                yield Static(
                    "[bold]Enter[/bold]  Open selected project\n"
                    "[bold]Ctrl+P[/bold]  Focus project list\n"
                    "[bold]Ctrl+H[/bold]  Global home\n"
                    "[bold]Q[/bold]  Quit"
                )
        yield Static("LOCAL-FIRST  •  GIT-NATIVE  •  NO AI REQUIRED", id="footer-note")
        yield Footer()
        with Container(id="intro"):
            yield Static("BREEZY TRACE", id="intro-copy")
            yield Static("", id="intro-kicker")

    def on_mount(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.add_columns("PROJECT", "PATH", "LAST OPENED")
        for project in self.registry.list_projects():
            table.add_row(
                project.name,
                project.path,
                project.last_opened_at or "Not opened yet",
                key=project.id,
            )
        if self.active_project:
            self.registry.mark_opened(self.active_project.id)
            self.show_project(self.active_project)
        else:
            self.query_one("#project-detail", Static).update(
                "Choose a registered project to inspect its current state.\n\n"
                f"[bold]{len(self.registry.list_projects())}[/bold] projects registered."
            )
        self._show_intro_brand()
        self.set_timer(0.62, self._show_intro_quote)

    def _set_intro(self, main: str, kicker: str = "") -> None:
        self.query_one("#intro-copy", Static).update(main)
        self.query_one("#intro-kicker", Static).update(kicker)

    def _show_intro_brand(self) -> None:
        self._set_intro("BREEZY TRACE")

    def _show_intro_quote(self) -> None:
        self._set_intro(
            "“Every project leaves a trail.\nMake yours meaningful.”",
            "A SMALL THOUGHT BEFORE YOU BEGIN",
        )
        self.set_timer(0.68, self._show_intro_credit)

    def _show_intro_credit(self) -> None:
        self._set_intro("FROM BREEZY LABS")
        self.set_timer(0.58, self._show_intro_wordmark)

    def _show_intro_wordmark(self) -> None:
        wordmark = (
            "█████  ████   ████  ████  ████\n"
            "  █    █   █  █  █  █     █\n"
            "  █    ████   ████  █     ███\n"
            "  █    █  █   █  █  █     █\n"
            "  █    █   █  █  █  ████  ████"
        )
        self._set_intro(wordmark, "B R E E Z Y   T R A C E")
        self.set_timer(0.82, self._finish_intro)

    def _finish_intro(self) -> None:
        intro = self.query_one("#intro")
        intro.styles.animate("opacity", 0.0, duration=0.24)
        self.set_timer(0.27, self._hide_intro)

    def _hide_intro(self) -> None:
        self.query_one("#intro").display = False

    def action_skip_intro(self) -> None:
        self._hide_intro()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        project_id = str(event.row_key.value)
        project = next(
            (item for item in self.registry.list_projects() if item.id == project_id),
            None,
        )
        if project:
            self.registry.mark_opened(project.id)
            self.active_project = project
            self.show_project(project)

    def show_project(self, project: Project) -> None:
        status = inspect_status(Path(project.path))
        git_details = branch_intelligence(Path(project.path))
        journal = JournalStore(self.registry.db_path)
        entries = journal.list_entries(project, limit=3)
        tasks = journal.list_tasks(project, status="open")
        decisions = journal.list_decisions(project, limit=2)
        recent_notes = "\n".join(
            f"• {entry['title']}" for entry in entries
        ) or "No notes yet — use: breezy-trace note TITLE"
        open_tasks = "\n".join(
            f"• {task['title']}" for task in tasks[:5]
        ) or "No open tasks"
        recent_decisions = "\n".join(
            f"• {item['title']}: {item['decision']}" for item in decisions
        ) or "No decisions recorded"
        detail = (
            f"[bold #BAE6FD]{project.name}[/bold #BAE6FD]\n"
            f"[dim]{project.path}[/dim]\n\n"
            f"[bold]Branch[/bold]\n{status.branch}\n\n"
            f"[bold]Git state[/bold]\n{status.summary}\n"
            f"Ahead: {status.ahead}  Behind: {status.behind}\n"
            f"Upstream: {git_details['upstream'] or 'not configured'}\n"
            f"Local branches: {len(git_details['local_branches'])}  Cached remote branches: {len(git_details['remote_branches'])}\n"
            f"Unpushed commits: {len(git_details['unpushed_commits'])}  Upstream-only: {len(git_details['upstream_only_commits'])}\n\n"
            f"[bold #38BDF8]RECENT NOTES[/bold #38BDF8]\n{recent_notes}\n\n"
            f"[bold #38BDF8]OPEN TASKS ({len(tasks)})[/bold #38BDF8]\n{open_tasks}\n\n"
            f"[bold #38BDF8]RECENT DECISIONS[/bold #38BDF8]\n{recent_decisions}\n\n"
            "[dim]Add context with: breezy-trace note, task, or decision.[/dim]"
        )
        self.query_one("#project-detail", Static).update(detail)

    def action_focus_projects(self) -> None:
        self.query_one("#project-table", DataTable).focus()

    def action_home(self) -> None:
        self.active_project = None
        self.query_one("#project-detail", Static).update(
            "[bold]Global overview[/bold]\n\n"
            f"{len(self.registry.list_projects())} registered projects.\n\n"
            "Select a project to view its current Git state."
        )
