"""Textual terminal workspace for Breezy Trace.

The interface is deliberately read-only with respect to Git. Journal and index
operations are explicit, local actions; no background watcher or network call
is started by opening the application.
"""

from contextlib import closing
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Static

from breezy_trace.activity import FileActivityStore
from breezy_trace.agents import AgentSessionStore
from breezy_trace.config import database_path
from breezy_trace.database import connect
from breezy_trace.git import branch_intelligence, inspect_details, inspect_status, recent_commits
from breezy_trace.journal import JournalStore
from breezy_trace.models import Project
from breezy_trace.polyglot_index import LANGUAGE_EXTENSIONS
from breezy_trace.registry import ProjectRegistry

THEME_CSS = """
Screen { layers: base overlay; background: #071426; color: #E1F2FF; }
Header { background: #102D50; color: #83CCFF; }
#hero { height: auto; padding: 1 2; margin: 1 1 0 1; border: round #234467; background: #102D50; }
#brand { color: #83CCFF; text-style: bold; }
#subtitle, #footer-note { color: #9ABBD6; }
#nav { height: 4; margin: 1 1 0 1; padding: 0 1; border: round #234467; align: center middle; }
#nav Button { min-width: 6; width: 1fr; height: 2; margin: 0; padding: 0 1; border: none; background: #102D50; color: #83CCFF; }
#nav Button:hover { background: #1D4F7A; color: #E1F2FF; }
#nav Button:focus { border: tall #83CCFF; }
#nav Button.active { background: #1D4F7A; color: #E1F2FF; text-style: bold; }
#workspace { layout: horizontal; height: 1fr; margin: 1 1 0 1; }
#project-list { width: 34%; min-width: 18; height: 1fr; }
#project-table { height: 1fr; border: round #234467; }
#content-panel { width: 1fr; border: round #234467; padding: 1 2; margin-left: 1; background: #0B1E35; }
#content-title { color: #83CCFF; text-style: bold; height: auto; margin-bottom: 1; }
#content { height: 1fr; overflow-y: auto; color: #E1F2FF; }
#footer-note { height: auto; padding: 0 2 1 2; }
#intro { layer: overlay; width: 100%; height: 100%; align: center middle; background: #071426; }
#intro-copy { width: 100%; height: auto; content-align: center middle; text-align: center; color: #83CCFF; text-style: bold; }
#intro-kicker { width: 100%; height: auto; content-align: center middle; text-align: center; color: #9ABBD6; }
"""

SCREEN_NAMES = {
    "1": ("home", "HOME"),
    "2": ("overview", "OVERVIEW"),
    "3": ("journal", "JOURNAL"),
    "4": ("agents", "AGENTS"),
    "5": ("git", "GIT"),
    "6": ("activity", "ACTIVITY"),
    "7": ("code", "CODE"),
    "8": ("settings", "SETTINGS"),
}


class TraceApp(App[None]):
    """Global project switcher and project intelligence workspace."""

    TITLE = "Breezy Trace"
    SUB_TITLE = "by Breezy Labs"
    CSS = THEME_CSS
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+p", "focus_projects", "Projects"),
        Binding("ctrl+h", "show_home", "Home"),
        Binding("1", "show_home", "Home", show=False),
        Binding("2", "show_overview", "Overview", show=False),
        Binding("3", "show_journal", "Journal", show=False),
        Binding("4", "show_agents", "Agents", show=False),
        Binding("5", "show_git", "Git", show=False),
        Binding("6", "show_activity", "Activity", show=False),
        Binding("7", "show_code", "Code", show=False),
        Binding("8", "show_settings", "Settings", show=False),
        Binding("space", "skip_intro", "Skip intro", show=False),
        Binding("escape", "show_home", "Back", show=False),
    ]

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.registry = ProjectRegistry()
        self.active_project = project
        self.current_view = "home"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="hero"):
            yield Static("BREEZY TRACE", id="brand", markup=False)
            yield Static(
                "A clear trail through your projects, code, and development history.",
                id="subtitle",
                markup=False,
            )
        with Horizontal(id="nav"):
            yield Button("Home", id="nav-home", tooltip="Home · press 1")
            yield Button("Project", id="nav-overview", tooltip="Project overview · press 2")
            yield Button("Journal", id="nav-journal", tooltip="Journal · press 3")
            yield Button("Agents", id="nav-agents", tooltip="Agent sessions · press 4")
            yield Button("Git", id="nav-git", tooltip="Git intelligence · press 5")
            yield Button("Activity", id="nav-activity", tooltip="File activity · press 6")
            yield Button("Code", id="nav-code", tooltip="Code intelligence · press 7")
            yield Button("Settings", id="nav-settings", tooltip="Settings · press 8")
        with Container(id="workspace"):
            with Vertical(id="project-list"):
                yield Static("YOUR PROJECTS", id="content-title", markup=False)
                yield DataTable(id="project-table", cursor_type="row")
            with Vertical(id="content-panel"):
                yield Static("HOME", id="view-title", markup=False)
                yield Static(id="content", markup=False)
        yield Static(
            "LOCAL-FIRST  ·  GIT-NATIVE  ·  NO AI REQUIRED  ·  NO TELEMETRY  ·  1–8 NAVIGATE  ·  Q QUIT",
            id="footer-note",
            markup=False,
        )
        yield Footer()
        with Container(id="intro"):
            yield Static("BREEZY TRACE", id="intro-copy", markup=False)
            yield Static("", id="intro-kicker", markup=False)

    def on_mount(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.add_columns("PROJECT", "BRANCH")
        self._apply_responsive_layout(self.size.width)
        projects = self.registry.list_projects()
        for item in projects:
            # Avoid spawning one Git process per registered project during startup.
            # Branch details are loaded only after the user opens a project.
            table.add_row(item.name, "select to inspect", key=item.id)
        if self.active_project:
            self.registry.mark_opened(self.active_project.id)
            self._render_view("overview")
        else:
            self._render_view("home")
        self._show_intro_brand()
        self.set_timer(0.9, self._show_intro_quote)

    def on_resize(self, event) -> None:
        """Switch the workspace between columns and stacked panels as it resizes."""
        self._apply_responsive_layout(event.size.width)

    def _apply_responsive_layout(self, width: int) -> None:
        workspace = self.query_one("#workspace", Container)
        project_list = self.query_one("#project-list", Vertical)
        content_panel = self.query_one("#content-panel", Vertical)
        nav_labels = (
            {
                "nav-home": "Home",
                "nav-overview": "Proj",
                "nav-journal": "Note",
                "nav-agents": "Agent",
                "nav-git": "Git",
                "nav-activity": "File",
                "nav-code": "Code",
                "nav-settings": "Set",
            }
            if width <= 80
            else {
                "nav-home": "Home",
                "nav-overview": "Project",
                "nav-journal": "Journal",
                "nav-agents": "Agents",
                "nav-git": "Git",
                "nav-activity": "Activity",
                "nav-code": "Code",
                "nav-settings": "Settings",
            }
        )
        for button_id, label in nav_labels.items():
            self.query_one(f"#{button_id}", Button).label = label
        if width <= 80:
            workspace.styles.layout = "vertical"
            project_list.styles.width = "100%"
            project_list.styles.height = 12
            project_list.styles.min_height = 7
            content_panel.styles.width = "100%"
            content_panel.styles.margin_left = 0
            content_panel.styles.min_height = 12
        else:
            workspace.styles.layout = "horizontal"
            project_list.styles.width = "34%"
            project_list.styles.height = "1fr"
            project_list.styles.min_height = 0
            content_panel.styles.width = "1fr"
            content_panel.styles.margin_left = 1
            content_panel.styles.min_height = 0

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
        self.set_timer(0.9, self._show_intro_credit)

    def _show_intro_credit(self) -> None:
        self._set_intro("FROM BREEZY LABS")
        self.set_timer(0.82, self._show_intro_wordmark)

    def _show_intro_wordmark(self) -> None:
        wordmark = (
            "╭──────────────╮\n"
            "│   B  /  T    │\n"
            "│   BREEZY     │\n"
            "│   TRACE      │\n"
            "╰──────────────╯"
        )
        self._set_intro(wordmark, "B R E E Z Y   T R A C E")
        self.set_timer(1.05, self._finish_intro)

    def _finish_intro(self) -> None:
        self.query_one("#intro").styles.animate("opacity", 0.0, duration=0.24)
        self.set_timer(0.27, self._hide_intro)

    def _hide_intro(self) -> None:
        self.query_one("#intro").display = False

    def action_skip_intro(self) -> None:
        self._hide_intro()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Make the compact icon navigation usable with mouse or keyboard focus."""
        view_by_button = {
            "nav-home": "home",
            "nav-overview": "overview",
            "nav-journal": "journal",
            "nav-agents": "agents",
            "nav-git": "git",
            "nav-activity": "activity",
            "nav-code": "code",
            "nav-settings": "settings",
        }
        view = view_by_button.get(event.button.id or "")
        if view:
            self._navigate(view)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        project_id = str(event.row_key.value)
        self.active_project = next(
            (item for item in self.registry.list_projects() if item.id == project_id),
            None,
        )
        if self.active_project:
            self.registry.mark_opened(self.active_project.id)
            self._render_view("overview")

    def _render(self, title: str, body: str) -> None:
        self.current_view = title.lower()
        self.query_one("#view-title", Static).update(title.upper())
        self.query_one("#content", Static).update(body)
        for button in self.query("#nav Button"):
            button.remove_class("active")
        self.query_one(f"#nav-{self.current_view}", Button).add_class("active")

    def _render_view(self, view: str) -> None:
        if view == "home":
            projects = self.registry.list_projects()
            if not projects:
                body = (
                    "WELCOME TO BREEZY TRACE\n\n"
                    "Your registered projects will appear in the list.\n\n"
                    "GET STARTED\n"
                    "From a Git repository, run: breezy-trace register .\n"
                    "Then launch breezy-trace from that repository.\n\n"
                    "WHAT'S INSIDE\n"
                    "Project overview  ·  Git status, diffs and recent commits\n"
                    "Journal           ·  Notes, tasks and decisions\n"
                    "Agent sessions    ·  Claude Code and OpenCode metadata\n"
                    "Git intelligence  ·  Branches, divergence and stashes\n"
                    "File activity     ·  Explicit change-history snapshots\n"
                    "Code intelligence ·  Symbols, imports and call sites\n"
                    "Settings          ·  Privacy, storage, backup and restore\n\n"
                    "CLI tools after registration: resume, inspect, branches,\n"
                    "sessions --sync, activity scan, code index/search/imports/calls,\n"
                    "backup, restore, notes, tasks and decisions."
                )
            else:
                body = (
                    "YOUR DEVELOPMENT WORKSPACE\n\n"
                    f"{len(projects)} registered project(s).\n\n"
                    "Select a project from the left to open its overview.\n\n"
                    "FEATURE DIRECTORY\n"
                    "Project overview     Git status, diffs, conflicts, stashes, commits\n"
                    "Journal              Notes, open/completed tasks, decisions\n"
                    "Agent sessions       Claude Code + OpenCode metadata (no transcripts)\n"
                    "Git intelligence     Branches, upstream divergence, cached refs\n"
                    "File activity        Explicit path/status history snapshots\n"
                    "Code intelligence    Symbols, imports, language support, call sites\n"
                    "Settings             Privacy boundaries, storage, backup and restore\n\n"
                    "QUICK COMMANDS (run inside this project)\n"
                    "resume · status · inspect · branches\n"
                    "note · task · tasks · done · decision · journal\n"
                    "sessions --sync · activity scan · activity log\n"
                    "code index · code languages · code search · code imports · code calls\n"
                    "backup · restore FILE --yes\n\n"
                    "Navigate with the buttons or number keys 1–8. Ctrl+P focuses projects."
                )
            self._render("Home", body)
            return

        project = self.active_project
        if project is None:
            self._render(
                view,
                "NO PROJECT SELECTED\n\nSelect a registered project from the list on the left.\n"
                "Only explicitly registered repositories are shown.",
            )
            return

        renderers = {
            "overview": self._overview,
            "journal": self._journal,
            "agents": self._agents,
            "git": self._git,
            "activity": self._activity,
            "code": self._code,
            "settings": self._settings,
        }
        renderer = renderers.get(view)
        self._render(view, renderer(project) if renderer else "Unknown workspace view.")

    def _overview(self, project: Project) -> str:
        status = inspect_status(Path(project.path))
        details = inspect_details(Path(project.path))
        commits = recent_commits(Path(project.path), limit=5)
        lines = [
            project.name,
            project.path,
            "",
            "WORKING TREE",
            status.summary,
            f"Branch: {status.branch}",
            f"Staged: {status.staged}    Modified: {status.modified}    Untracked: {status.untracked}",
            f"Ahead: {status.ahead}    Behind: {status.behind}",
            (
                f"Conflicts: {details['conflicts']}    Stashes: {details['stashes']}"
                if details.get("available", True)
                else "Git details unavailable (command failed or timed out)"
            ),
            "",
            "RECENT LOCAL COMMITS",
        ]
        lines.extend(
            f"{item['sha']}  {item['date']}  {item['subject']}" for item in commits
        )
        if not commits:
            lines.append("No local commits found.")
        lines.extend(["", "RESUME YOUR WORK", "Use the Journal screen to record what you did, why, and what comes next."])
        return "\n".join(lines)

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
        lines.extend(
            f"• {row['title']}  [{row['created_at'][:10]}]" for row in notes
        )
        if not notes:
            lines.append("No notes recorded. Try: breezy-trace note \"Next session\" --body \"...\"")
        lines.extend(["", f"OPEN TASKS ({sum(row['status'] == 'open' for row in tasks)})"])
        lines.extend(f"□ {row['title']}" for row in tasks if row["status"] == "open")
        if not any(row["status"] == "open" for row in tasks):
            lines.append("No open tasks.")
        lines.extend(["", "RECENT DECISIONS"])
        lines.extend(f"• {row['title']}: {row['decision']}" for row in decisions)
        if not decisions:
            lines.append("No decisions recorded.")
        lines.extend(["", "CLI: note TITLE · task TITLE · tasks [--all] · done TASK_ID", "CLI: decision TITLE DECISION · journal · resume"])
        return "\n".join(lines)

    def _agents(self, project: Project) -> str:
        sessions = AgentSessionStore(self.registry.db_path).list_sessions(project, limit=20)
        lines = [
            "AGENT SESSION HISTORY",
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
        lines.extend(["", "Supported discovery: Claude Code and OpenCode.", "Refresh metadata: breezy-trace sessions --sync"])
        return "\n".join(lines)

    def _git(self, project: Project) -> str:
        data = branch_intelligence(Path(project.path))
        status = inspect_status(Path(project.path))
        if not data.get("available", True):
            return "GIT INTELLIGENCE · READ ONLY\n\nGit is unavailable or the inspection timed out."
        lines = [
            "GIT INTELLIGENCE · READ ONLY",
            f"Current branch: {status.branch}",
            f"Upstream: {data['upstream'] or 'not configured'}",
            f"Ahead: {data['ahead'] if data['ahead'] is not None else 'unknown'} | Behind: {data['behind'] if data['behind'] is not None else 'unknown'}",
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
        lines.extend(f"• {item['sha']}  {item['subject']}" for item in data["upstream_only_commits"])
        lines.extend(["", f"STASHES ({len(data['stashes'])})"])
        lines.extend(f"• {item['ref']}  {item['subject']}" for item in data["stashes"])
        return "\n".join(lines)

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
            lines.extend([
                "No activity snapshots recorded.",
                "Run: breezy-trace activity scan",
            ])
        lines.extend(["", "Commands: breezy-trace activity scan · breezy-trace activity log", "Scanning is explicit; no background watcher is running."])
        return "\n".join(lines)

    def _code(self, project: Project) -> str:
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
        lines.extend(["", "COMMANDS", "breezy-trace code index", "breezy-trace code languages", "breezy-trace code search QUERY", "breezy-trace code imports [QUERY]", "breezy-trace code calls [QUERY]"])
        return "\n".join(lines)

    def _settings(self, project: Project) -> str:
        return "\n".join([
            "LOCAL SETTINGS & PRIVACY",
            "",
            f"Active project: {project.name}",
            f"Project path: {project.path}",
            f"Local database: {database_path()}",
            "",
            "PRIVACY BOUNDARIES",
            "• Project metadata and journal data stay in your local SQLite database.",
            "• Git inspection is read-only; Breezy Trace never fetches or changes branches.",
            "• Agent integrations store allowlisted session metadata, not transcripts.",
            "• Code indexing stores symbols, imports, paths and hashes, not source text.",
            "• No telemetry or mandatory AI provider.",
            "",
            "BACKUP & RESTORE",
            "Create a portable backup: breezy-trace backup",
            "Restore explicitly: breezy-trace restore FILE --yes",
            "Inspect this project: breezy-trace status · inspect · branches · resume",
            "",
            "INTEGRATIONS",
            "Claude Code and OpenCode metadata discovery are available.",
            "Other editor integrations are not yet implemented.",
        ])

    def _navigate(self, view: str) -> None:
        self._render_view(view)

    def action_show_home(self) -> None:
        self._navigate("home")

    def action_show_overview(self) -> None:
        self._navigate("overview")

    def action_show_journal(self) -> None:
        self._navigate("journal")

    def action_show_agents(self) -> None:
        self._navigate("agents")

    def action_show_git(self) -> None:
        self._navigate("git")

    def action_show_activity(self) -> None:
        self._navigate("activity")

    def action_show_code(self) -> None:
        self._navigate("code")

    def action_show_settings(self) -> None:
        self._navigate("settings")

    def action_focus_projects(self) -> None:
        self.query_one("#project-table", DataTable).focus()
