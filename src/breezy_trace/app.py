"""Textual terminal interface for Breezy Trace."""

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from breezy_trace.git import inspect_status
from breezy_trace.models import Project
from breezy_trace.registry import ProjectRegistry

THEME_CSS = """
Screen {
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
        detail = (
            f"[bold #BAE6FD]{project.name}[/bold #BAE6FD]\n"
            f"[dim]{project.path}[/dim]\n\n"
            f"[bold]Branch[/bold]\n{status.branch}\n\n"
            f"[bold]Git state[/bold]\n{status.summary}\n"
            f"Ahead: {status.ahead}  Behind: {status.behind}\n\n"
            "[dim]Project journal and agent history are next in the build sequence.[/dim]"
        )
        self.query_one("#project-detail", Static).update(detail)

    def action_focus_projects(self) -> None:
        self.query_one("#project-table", DataTable).focus()

    def action_home(self) -> None:
        self.active_project = None
        self.query_one("#project-detail", Static).update(
            f"[bold]Global overview[/bold]\n\n"
            f"{len(self.registry.list_projects())} registered projects.\n\n"
            "Select a project to view its current Git state."
        )
