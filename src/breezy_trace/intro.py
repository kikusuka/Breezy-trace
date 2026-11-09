"""Boot sequence.

A scan sweeps the TRACE logo into place, a line draws beneath it with one node per
project (each node takes its project's Git-state colour as the data arrives), and a
short boot log reports what was really loaded. Any key or click skips it.

It doubles as the loading screen: it ends once the animation has played and every
project has reported in, with a hard cap so a slow repository can never hold it up.
"""

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from breezy_trace.theme import BLUE_RAMP, LOGO_ROW_COLORS, PALETTE
from breezy_trace.visuals import CHECK, LOGO_WIDTH, SPINNER, logo_frame, reveal_text, trace_path

KICKER = "B R E E Z Y"
SMALL_TITLE = "T R A C E"

TICK_SECONDS = 0.04
LOGO_START = 6
PATH_START = 14
LOG_STARTS = (20, 26)
ATTENTION_START = 32
HOLD_TICKS = 14
MIN_TICKS = 46
MAX_TICKS = 90
ART_WIDTH = 56
LOG_WIDTH = 36
MAX_NODES = 9


def _centered(text: str, width: int) -> str:
    return " " * max(0, (width - len(text)) // 2) + text


class IntroScreen(Screen[None]):
    """Full-screen welcome that doubles as the loading screen."""

    CSS = """
    IntroScreen { align: center middle; background: $tr-bg; }
    #intro-art { width: 56; height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._tick = 0
        self._done = False
        self._ready_tick: int | None = None
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Static(id="intro-art", markup=False)

    def on_mount(self) -> None:
        self._draw()
        self._timer = self.set_interval(TICK_SECONDS, self._advance)

    def _advance(self) -> None:
        self._tick += 1
        ready = self._draw()
        if ready and self._ready_tick is None:
            self._ready_tick = self._tick
        if self._tick >= MAX_TICKS:
            self._finish()
        elif ready and self._tick >= MIN_TICKS:
            shown = max(self._ready_tick or 0, ATTENTION_START)
            if self._tick >= shown + HOLD_TICKS:
                self._finish()

    # ------------------------------------------------------------------ drawing

    def _logo_lines(self, tick: int, width: int) -> list[Text]:
        if width < LOGO_WIDTH:
            return [Text(_centered(reveal_text(SMALL_TITLE, tick, LOGO_START), width),
                         style=f"bold {PALETTE['ice']}")]
        pad = " " * ((width - LOGO_WIDTH) // 2)
        kind_styles = {
            "flash": f"bold {PALETTE['text']}",
            "trail": f"bold {PALETTE['ice']}",
        }
        lines: list[Text] = []
        for row_index, row in enumerate(logo_frame(tick, start=LOGO_START)):
            line = Text(pad)
            for char, kind in row:
                style = kind_styles.get(kind) or f"bold {LOGO_ROW_COLORS[row_index]}"
                line.append(char, style=style)
            lines.append(line)
        return lines

    def _path_line(
        self, tick: int, width: int, total: int, colors: list[str | None]
    ) -> Text:
        line = Text()
        if tick < PATH_START:
            return line
        nodes = max(2, min(total, MAX_NODES)) if total else 3
        cells = trace_path(tick - PATH_START, width, nodes)
        last = len(BLUE_RAMP) - 1
        for x, (char, node) in enumerate(cells):
            if node >= 0:
                color = colors[node] if node < len(colors) and colors[node] else PALETTE["ice"]
                line.append(char, style=f"bold {color}")
            else:
                line.append(char, style=BLUE_RAMP[min(last, x * len(BLUE_RAMP) // max(1, width))])
        return line

    def _log_lines(
        self, tick: int, width: int, total: int, loaded: int, attention: int, ready: bool
    ) -> list[Text]:
        pad = " " * max(0, (width - LOG_WIDTH) // 2)
        lines: list[Text] = []

        def entry(icon: str, color: str, label: str, value: str, value_color: str) -> Text:
            line = Text(pad)
            line.append(f"{icon} ", style=f"bold {color}")
            line.append(f"{label:<11}", style=PALETTE["muted"])
            line.append(value, style=value_color)
            return line

        if tick >= LOG_STARTS[0]:
            value = "empty" if total == 0 else f"{total} project{'s' if total != 1 else ''}"
            lines.append(entry(CHECK, PALETTE["clean"], "registry", value, PALETTE["text"]))
        else:
            lines.append(Text())
        if tick >= LOG_STARTS[1] and total:
            if ready:
                lines.append(entry(CHECK, PALETTE["clean"], "git state",
                                   f"{total}/{total}", PALETTE["text"]))
            else:
                lines.append(entry(SPINNER[tick % len(SPINNER)], PALETTE["primary"],
                                   "git state", f"{loaded}/{total}", PALETTE["muted"]))
        else:
            lines.append(Text())
        if tick >= ATTENTION_START and ready:
            if total == 0:
                lines.append(entry("›", PALETTE["primary"], "next",
                                   "press o to add a repository", PALETTE["text"]))
            elif attention:
                lines.append(entry("!", PALETTE["dirty"], "attention",
                                   f"{attention} need attention", PALETTE["dirty"]))
            else:
                lines.append(entry(CHECK, PALETTE["clean"], "attention",
                                   "all clean", PALETTE["clean"]))
        else:
            lines.append(Text())
        return lines

    def _draw(self) -> bool:
        """Render the current frame; return whether every project has reported in."""
        tick = self._tick
        width = min(ART_WIDTH, max(24, self.size.width - 4))
        total, loaded, attention, colors = self.app.boot_status()
        ready = total == 0 or loaded >= total

        art = self.query_one("#intro-art", Static)
        art.styles.width = width
        lines: list[Text] = [
            Text(_centered(reveal_text(KICKER, tick, 0), width), style=f"bold {PALETTE['muted']}")
        ]
        lines.extend(self._logo_lines(tick, width))
        lines.append(Text())
        lines.append(self._path_line(tick, width, total, colors))
        lines.append(Text())
        lines.extend(self._log_lines(tick, width, total, loaded, attention, ready))
        lines.append(Text())
        lines.append(Text(_centered("any key to skip", width), style=PALETTE["faint"]))
        art.update(Text("\n").join(lines))
        return ready

    # ------------------------------------------------------------------ control

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        if self._timer is not None:
            self._timer.stop()
        self.app.pop_screen()

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self._finish()

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self._finish()
