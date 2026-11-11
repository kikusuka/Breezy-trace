"""Dialogs: data-entry form, task chooser and the universal help screen."""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from breezy_trace.theme import PALETTE, current_theme, theme_label
from breezy_trace.visuals import CHECK

DIALOG_CSS = """
#form-dialog, #choice-dialog {
    width: 72; max-width: 94%; height: auto; max-height: 90%;
    border: round $tr-primary; background: $tr-surface; padding: 1 2;
}
#form-title, #choice-title { color: $tr-primary; text-style: bold; height: auto; }
.form-label { color: $tr-muted; height: 1; margin-top: 1; }
#form-hint { color: $tr-faint; height: auto; margin-top: 1; }
#form-actions { height: 3; margin-top: 1; align: right middle; }
#form-actions Button { margin-left: 1; }
#choice-list { height: auto; max-height: 14; margin-top: 1; background: $tr-surface; border: round $tr-border; }
"""


class FormScreen(ModalScreen["dict[str, str] | None"]):
    """A small form. Enter moves to the next field and saves on the last one."""

    CSS = "FormScreen { align: center middle; background: $tr-bg 70%; }" + DIALOG_CSS
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        fields: list[tuple[str, str, str]],
        hint: str = "",
        required: tuple[str, ...] | None = None,
        defaults: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._fields = fields
        self._hint = hint
        self._required = required if required is not None else (fields[0][0],)
        self._defaults = defaults or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="form-dialog"):
            yield Static(self._title, id="form-title", markup=False)
            for key, label, placeholder in self._fields:
                yield Static(label, classes="form-label", markup=False)
                yield Input(
                    value=self._defaults.get(key, ""), placeholder=placeholder, id=f"field-{key}"
                )
            if self._hint:
                yield Static(self._hint, id="form-hint", markup=False)
            with Horizontal(id="form-actions"):
                yield Button("Save", id="form-save", variant="primary")
                yield Button("Cancel", id="form-cancel")

    def on_mount(self) -> None:
        self.query(Input).first().focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        inputs = list(self.query(Input))
        index = inputs.index(event.input)
        if index < len(inputs) - 1:
            inputs[index + 1].focus()
        else:
            self._save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "form-cancel":
            self.dismiss(None)
        else:
            self._save()

    def _save(self) -> None:
        values = {
            key: self.query_one(f"#field-{key}", Input).value.strip()
            for key, _label, _placeholder in self._fields
        }
        for key, label, _placeholder in self._fields:
            if key in self._required and not values[key]:
                self.app.notify(f"{label} is required.", severity="warning")
                self.query_one(f"#field-{key}", Input).focus()
                return
        self.dismiss(values)


class ConfirmScreen(ModalScreen[bool]):
    """Yes/no question for anything destructive. Cancel is focused first, so Enter is safe."""

    CSS = """
    ConfirmScreen { align: center middle; background: $tr-bg 70%; }
    #confirm-dialog {
        width: 74; max-width: 94%; height: auto; max-height: 90%;
        border: round $tr-danger; background: $tr-surface; padding: 1 2;
    }
    #confirm-title { color: $tr-danger; text-style: bold; height: auto; margin-bottom: 1; }
    #confirm-body { height: auto; }
    #confirm-actions { height: 3; margin-top: 1; align: right middle; }
    #confirm-actions Button { margin-left: 1; }
    """
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, lines: list[str], confirm_label: str = "Remove") -> None:
        super().__init__()
        self._title = title
        self._lines = lines
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self._title, id="confirm-title", markup=False)
            yield Static(Text("\n".join(self._lines)), id="confirm-body")
            with Horizontal(id="confirm-actions"):
                yield Button(self._confirm_label, id="confirm-yes", variant="error")
                yield Button("Cancel", id="confirm-no", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#confirm-no", Button).focus()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class ChoiceScreen(ModalScreen["str | None"]):
    """Pick one item from a short list; returns the chosen id."""

    CSS = "ChoiceScreen { align: center middle; background: $tr-bg 70%; }" + DIALOG_CSS
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, options: list[tuple[str, str]]) -> None:
        super().__init__()
        self._title = title
        self._options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-dialog"):
            yield Static(self._title, id="choice-title", markup=False)
            yield OptionList(
                *[Option(Text(label), id=option_id) for option_id, label in self._options],
                id="choice-list",
            )
            yield Static("Enter to choose · Esc to cancel", id="form-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#choice-list", OptionList).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)


HELP_KEYS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Navigate",
        (
            ("Enter", "Open the selected project (lobby)"),
            ("↑ ↓", "Move through projects; scroll a page"),
            ("Esc", "Back to the lobby; close any dialog"),
            ("1 … 7", "Resume · Metrics · Journal · Git · Activity · Code · Settings"),
            (
                "o",
                "Add a repository that already exists on this machine (lobby)  ·  CLI: breezy-trace register PATH",
            ),
            (
                "n (lobby)",
                "New project: makes a folder with an empty Git repository and adds it  ·  CLI: breezy-trace new NAME",
            ),
            (
                "c (lobby)",
                "Clone from a GitHub / GitLab / any Git URL and add it  ·  CLI: breezy-trace clone URL",
            ),
            (
                "Delete",
                "Remove the highlighted project from Trace; asks first and never touches your files  ·  CLI: breezy-trace unregister NAME",
            ),
            ("w", "Open the project's GitHub / GitLab page in your browser (inside a project)"),
            (
                "v",
                "Open the project in your editor (VS Code, Cursor, ...), File Explorer or a terminal (inside a project)",
            ),
            (
                "R",
                "Run one of the project's own commands: pytest, npm scripts, cargo, go, gradle, make, dotnet (inside a project)",
            ),
            (
                "u",
                "Standup across all projects: commits, finished tasks, what is next; press again for 3 and 7 days  ·  CLI: breezy-trace standup [--days N]",
            ),
            (
                "/",
                "Search notes, tasks and decisions in every project  ·  CLI: breezy-trace search QUERY",
            ),
            ("r", "Refresh the current view"),
            ("T / F2", "Switch theme: blue / midnight blue (remembered)"),
            ("? / F1", "This help, from anywhere"),
            ("q", "Quit"),
        ),
    ),
    (
        "Do things (inside a project; every key works on every tab)",
        (
            ("n", 'New note  ·  CLI: breezy-trace note "Title" --body "..."'),
            (
                "N",
                "Write a note in your own editor ($VISUAL / $EDITOR)  ·  CLI: breezy-trace note  (no title)",
            ),
            ("t", 'New task  ·  CLI: breezy-trace task "Title"'),
            ("d", 'Record a decision  ·  CLI: breezy-trace decision "Title" "Decision"'),
            ("x", "Complete a task  ·  CLI: breezy-trace done TASK_ID"),
            ("i", "Index code symbols and imports  ·  CLI: breezy-trace code index"),
            ("a", "Scan the working tree for file activity  ·  CLI: breezy-trace activity scan"),
            (
                "s",
                "Sync Claude Code / OpenCode session metadata  ·  CLI: breezy-trace sessions --sync",
            ),
            (
                "m",
                "Turn TODO/FIXME comments into tasks, never duplicating  ·  CLI: breezy-trace todos [--import]",
            ),
            (
                "e",
                "Export a Markdown handoff for any agent or teammate  ·  CLI: breezy-trace handoff [--out FILE]",
            ),
            ("b", "Back up the local database (any screen)  ·  CLI: breezy-trace backup"),
        ),
    ),
    (
        "Also from the shell",
        (
            ("status", "breezy-trace status · inspect · branches · resume"),
            (
                "code",
                "breezy-trace code search QUERY · imports [QUERY] · calls [QUERY] · languages",
            ),
            (
                "open",
                "breezy-trace open [PATH]  adds a folder if needed (offers git init for plain folders) and opens it",
            ),
            (
                "explorer",
                "breezy-trace integrate install|uninstall|status  adds a right-click 'Open with Breezy Trace' to Windows Explorer",
            ),
            (
                "prompt",
                "breezy-trace prompt --init powershell|bash|zsh|starship  prints setup for a prompt that shows the project state",
            ),
            ("journal", "breezy-trace journal · tasks [--all] · activity log · sessions"),
            ("projects", "breezy-trace register PATH · unregister · projects · restore FILE --yes"),
        ),
    ),
    (
        "Reading the screen",
        (
            (
                "●",
                "Project state: green clean · amber uncommitted · blue unpushed · coral behind · grey unknown",
            ),
            (
                f"± ↑ ↓ {CHECK}",
                f"± changed files · ↑ commits not pushed · ↓ commits behind upstream · {CHECK} clean",
            ),
            ("30 DAYS", "Commits per 3-day block; taller (or darker) is busier (sparkline)"),
            (
                "■ grid",
                "Commits per week for 12 weeks; darker blue is busier, scaled across all projects",
            ),
            (
                "Since you…",
                "Resume: commits, authors and line changes since you last opened the project",
            ),
            ("Branch graph", "Git tab: commit lanes with branch, remote and tag labels"),
            (
                "Dependency map",
                "Code tab (after indexing): which Python modules import which, hubs and cycles",
            ),
            ("TODO / FIXME", "Metrics tab: comment markers found by git grep in tracked files"),
            ("Streak", "Consecutive days with a commit; a quiet today does not break it yet"),
            ("Churn", "Lines added and removed over 30 days, summed from Git history"),
            ("Hot files", "Files changed in the most commits over 30 days"),
            ("Rhythm", "When commits happen, by weekday and hour, in the author's local time"),
        ),
    ),
)


def build_help_text() -> Text:
    out = Text()
    out.append("Breezy Trace", style=f"bold {PALETTE['primary']}")
    out.append("  ·  project memory for the terminal\n", style=PALETTE["muted"])
    out.append(
        "Local-first: your data stays on this machine. Git is only ever read, never changed.\n",
        style=PALETTE["muted"],
    )
    for title, rows in HELP_KEYS:
        out.append(f"\n{title.upper()}\n", style=f"bold {PALETTE['primary']}")
        width = max(len(key) for key, _ in rows) + 2
        for key, meaning in rows:
            out.append(f"{key:<{width}}", style=f"bold {PALETTE['ice']}")
            out.append(f"{meaning}\n", style=PALETTE["text"])
    out.append("\nTHEME\n", style=f"bold {PALETTE['primary']}")
    out.append(f"{theme_label(current_theme())}", style=PALETTE["text"])
    out.append("   (T or F2 to switch; remembered next time)\n", style=PALETTE["muted"])
    return out


class HelpScreen(ModalScreen[None]):
    """Universal help: every key, every manual feature, and how to read the screen."""

    CSS = """
    HelpScreen { align: center middle; background: $tr-bg 70%; }
    #help-dialog {
        width: 96%; max-width: 110; height: 92%;
        border: round $tr-primary; background: $tr-surface; padding: 0 2;
        border-title-color: $tr-primary; border-title-style: bold;
        scrollbar-size-vertical: 1;
    }
    #help-foot { height: 1; padding: 0 2; background: $tr-surface; color: $tr-faint; }
    """
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "Close"),
        Binding("question_mark", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-dialog"):
            yield Static(build_help_text(), id="help-body")
        yield Static("Esc, ? or F1 to close · ↑ ↓ to scroll", id="help-foot", markup=False)

    def on_mount(self) -> None:
        self.query_one("#help-dialog").border_title = "HELP"

    def action_close(self) -> None:
        self.dismiss(None)
