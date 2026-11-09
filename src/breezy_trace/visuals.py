"""Pure helpers for terminal charts and animation frames (no UI imports)."""

import math
import os
import sys
from collections.abc import Sequence
from datetime import date, timedelta

SPARK_FULL = "▁▂▃▄▅▆▇█"
SPARK_BASIC = "·░▒▓█"
SPARK_LEVELS = SPARK_FULL


def basic_glyphs() -> bool:
    """True where the font probably lacks thin block and braille characters.

    The classic Windows console (Consolas) draws them as empty boxes, Windows Terminal
    does not. Override with BREEZY_TRACE_GLYPHS=basic or =full.
    """
    mode = os.environ.get("BREEZY_TRACE_GLYPHS", "").strip().lower()
    if mode == "basic":
        return True
    if mode == "full":
        return False
    return sys.platform == "win32" and not os.environ.get("WT_SESSION")


BASIC = basic_glyphs()
CHECK = "√" if BASIC else "✓"
SPINNER = "|/-\\" if BASIC else "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def sparkline(values: Sequence[int], basic: bool | None = None) -> str:
    """One block character per value; zero is the lowest level, any activity is higher."""
    if not values:
        return ""
    levels = SPARK_BASIC if (BASIC if basic is None else basic) else SPARK_FULL
    peak = max(values)
    if peak <= 0:
        return levels[0] * len(values)
    top = len(levels) - 2
    return "".join(
        levels[0] if value <= 0 else levels[1 + round(value / peak * top)] for value in values
    )


def heat_level(value: int, peak: int) -> int:
    """Map a count onto 0-4; any non-zero count is at least level 1."""
    if value <= 0 or peak <= 0:
        return 0
    return max(1, min(4, math.ceil(4 * value / peak)))


def bar(value: int, peak: int, width: int) -> str:
    if value <= 0 or peak <= 0 or width <= 0:
        return ""
    return "█" * max(1, round(width * value / peak))


def bucket_days(counts: dict[date, int], days: int, today: date) -> list[int]:
    """Daily counts, oldest first, ending on ``today``."""
    return [counts.get(today - timedelta(days=days - 1 - index), 0) for index in range(days)]


def rebucket(values: Sequence[int], size: int) -> list[int]:
    """Sum fixed-size groups, aligned to the newest value (leftovers at the old end drop)."""
    if size <= 0:
        raise ValueError("Bucket size must be positive.")
    groups = len(values) // size
    tail = list(values)[len(values) - groups * size :]
    return [sum(tail[index * size : (index + 1) * size]) for index in range(groups)]


_FONT = {
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
    "R": ("████ ", "█   █", "████ ", "█  █ ", "█   █"),
    "A": (" ███ ", "█   █", "█████", "█   █", "█   █"),
    "C": (" ████", "█    ", "█    ", "█    ", " ████"),
    "E": ("█████", "█    ", "████ ", "█    ", "█████"),
}
LOGO_ROWS: tuple[str, ...] = tuple(
    " ".join(_FONT[letter][row] for letter in "TRACE") for row in range(5)
)
LOGO_WIDTH = len(LOGO_ROWS[0])


def logo_frame(
    tick: int, start: int = 0, speed: int = 2, trail: int = 5
) -> list[list[tuple[str, str]]]:
    """Block-letter logo under a left-to-right scan.

    Each cell is ``(char, kind)``: ``hidden`` (not reached yet), ``flash`` (the scan
    head), ``trail`` (just behind it) or ``settled`` (final colour by row).
    """
    scan = (tick - start) * speed
    frame: list[list[tuple[str, str]]] = []
    for row in LOGO_ROWS:
        cells: list[tuple[str, str]] = []
        for x, char in enumerate(row):
            behind = scan - x
            if char == " " or behind < 0:
                cells.append((" ", "hidden"))
            elif behind <= 1:
                cells.append((char, "flash"))
            elif behind <= trail:
                cells.append((char, "trail"))
            else:
                cells.append((char, "settled"))
        frame.append(cells)
    return frame


def node_positions(width: int, nodes: int) -> list[int]:
    if nodes <= 1:
        return [width // 2]
    return sorted({round(index * (width - 1) / (nodes - 1)) for index in range(nodes)})


def trace_path(tick: int, width: int, nodes: int, ticks: int = 18) -> list[tuple[str, int]]:
    """A line that draws left to right with ``●`` nodes; each cell is ``(char, node_index)``.

    ``node_index`` is -1 for line segments and blanks, so callers can colour each node
    (for example by the Git state of the project it stands for).
    """
    reach = round(width * min(max(tick, 0), ticks) / ticks)
    positions = node_positions(width, nodes)
    cells: list[tuple[str, int]] = []
    for x in range(width):
        if x >= reach:
            cells.append((" ", -1))
        elif x in positions:
            cells.append(("●", positions.index(x)))
        else:
            cells.append(("─", -1))
    return cells


def stacked_cells(values: Sequence[int], width: int) -> list[int]:
    """Split ``width`` cells across ``values`` proportionally (largest remainder)."""
    total = sum(values)
    if total <= 0 or width <= 0:
        return [0] * len(values)
    exact = [value * width / total for value in values]
    cells = [int(share) for share in exact]
    order = sorted(range(len(values)), key=lambda i: exact[i] - cells[i], reverse=True)
    for index in order[: width - sum(cells)]:
        cells[index] += 1
    return cells


def reveal_text(text: str, tick: int, start: int) -> str:
    """Letters of ``text`` revealed one per tick after ``start``."""
    return text[: max(0, min(len(text), tick - start))]
