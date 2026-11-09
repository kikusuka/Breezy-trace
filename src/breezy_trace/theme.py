"""Breezy Trace themes and Git-state presentation rules.

Colour carries meaning here, never decoration: green is clean, amber is uncommitted
work, coral needs attention, blue is Breezy identity and unpushed commits, violet marks
decisions. Two blue themes ship: ``sky`` (light blue, the default) and ``midnight``
(dark blue). This module has no UI-framework imports so the rules stay testable.

``PALETTE``, ``HEAT``, ``BLUE_RAMP``, ``LOGO_ROW_COLORS`` and ``CATEGORY`` are mutated
in place by :func:`apply_theme`, so every module that imported them sees the active theme.
"""

from breezy_trace.models import GitStatus
from breezy_trace.visuals import CHECK

THEMES: dict[str, dict] = {
    "sky": {
        "label": "Breezy Light (logo aqua-blue)",
        "light": True,
        "palette": {
            "bg": "#3E9FD8",
            "surface": "#6FD3E0",
            "raised": "#B4F1F5",
            "border": "#0B6FA8",
            "border-focus": "#031A3D",
            "text": "#031A3D",
            "muted": "#0A3A66",
            "faint": "#1F5F8F",
            "primary": "#0B4DB8",
            "ice": "#073A8C",
            "clean": "#00704A",
            "dirty": "#8F4A00",
            "danger": "#B3002D",
            "ahead": "#0B4DB8",
            "decision": "#5B2DB8",
        },
        "heat": ("#5BC2D6", "#3AA3D0", "#1B7DC4", "#0B55A8", "#06306B"),
        "ramp": ("#0B5AA8", "#0A4A94", "#083A80", "#052B6B", "#031A3D"),
        "logo": ("#031A3D", "#052A5C", "#073B7C", "#0A4B98", "#0E5BB0"),
        "category": ("#0B4DB8", "#031A3D", "#5B2DB8", "#00796B", "#A61E6E", "#1F5F8F"),
    },
    "midnight": {
        "label": "Breezy Dark (website navy)",
        "light": False,
        "palette": {
            "bg": "#04122E",
            "surface": "#0A1E45",
            "raised": "#133070",
            "border": "#1D4286",
            "border-focus": "#6DD5DD",
            "text": "#E8F0FF",
            "muted": "#9DB1D6",
            "faint": "#6C84B0",
            "primary": "#4D94FF",
            "ice": "#6DD5DD",
            "clean": "#3DDC97",
            "dirty": "#FFB547",
            "danger": "#FF6B7F",
            "ahead": "#4D94FF",
            "decision": "#B79BFF",
        },
        "heat": ("#102A5C", "#1D4FA3", "#2F7AE0", "#6DB0FF", "#BFF3F6"),
        "ramp": ("#1D4FA3", "#2F7AE0", "#4D94FF", "#6DD5DD", "#BFF3F6"),
        "logo": ("#BFF3F6", "#6DD5DD", "#4D94FF", "#3C7FE6", "#2F6BD0"),
        "category": ("#4D94FF", "#6DD5DD", "#B79BFF", "#4FD1C5", "#7C9CFF", "#6C84B0"),
    },
}
DEFAULT_THEME = "sky"

PALETTE: dict[str, str] = {}
HEAT: list[str] = []
BLUE_RAMP: list[str] = []
LOGO_ROW_COLORS: list[str] = []
CATEGORY: list[str] = []
_active = DEFAULT_THEME


def apply_theme(name: str) -> str:
    """Make ``name`` the active theme (unknown names fall back to the default)."""
    global _active
    if name not in THEMES:
        name = DEFAULT_THEME
    spec = THEMES[name]
    PALETTE.clear()
    PALETTE.update(spec["palette"])
    HEAT[:] = spec["heat"]
    BLUE_RAMP[:] = spec["ramp"]
    LOGO_ROW_COLORS[:] = spec["logo"]
    CATEGORY[:] = spec["category"]
    _active = name
    return name


def current_theme() -> str:
    return _active


def theme_label(name: str) -> str:
    return THEMES.get(name, THEMES[DEFAULT_THEME])["label"]


def is_light_theme(name: str | None = None) -> bool:
    return bool(THEMES.get(name or _active, THEMES[DEFAULT_THEME])["light"])


def next_theme(name: str) -> str:
    names = list(THEMES)
    return names[(names.index(name) + 1) % len(names)] if name in names else DEFAULT_THEME


def css_variables() -> dict[str, str]:
    """Active palette as Textual CSS variables (``$tr-bg``, ``$tr-primary``, ...)."""
    return {f"tr-{name}": value for name, value in PALETTE.items()}


def is_unavailable(status: GitStatus) -> bool:
    return status.branch == "unknown"


def changed_count(status: GitStatus) -> int:
    return status.staged + status.modified + status.untracked


def needs_attention(status: GitStatus) -> bool:
    if is_unavailable(status):
        return False
    return changed_count(status) > 0 or status.ahead > 0 or status.behind > 0


def state_color(status: GitStatus) -> str:
    """Single colour summarising a repository, most urgent state first."""
    if is_unavailable(status):
        return PALETTE["faint"]
    if status.behind > 0:
        return PALETTE["danger"]
    if changed_count(status) > 0:
        return PALETTE["dirty"]
    if status.ahead > 0:
        return PALETTE["ahead"]
    return PALETTE["clean"]


def state_segments(status: GitStatus) -> list[tuple[str, str]]:
    """Compact ``(text, colour)`` pieces such as ``±3 ↑2 ↓1`` or a check mark."""
    if is_unavailable(status):
        return [("?", PALETTE["faint"])]
    segments: list[tuple[str, str]] = []
    changed = changed_count(status)
    if changed:
        segments.append((f"±{changed}", PALETTE["dirty"]))
    if status.ahead:
        segments.append((f"↑{status.ahead}", PALETTE["ahead"]))
    if status.behind:
        segments.append((f"↓{status.behind}", PALETTE["danger"]))
    return segments or [(CHECK, PALETTE["clean"])]


def attention_reasons(status: GitStatus) -> list[str]:
    reasons: list[str] = []
    changed = changed_count(status)
    if changed:
        reasons.append(f"{changed} uncommitted")
    if status.ahead:
        reasons.append(f"{status.ahead} unpushed")
    if status.behind:
        reasons.append(f"{status.behind} behind")
    return reasons


def attention_rank(status: GitStatus) -> int:
    """Lower sorts first: behind, then dirty, then unpushed."""
    if status.behind > 0:
        return 0
    if changed_count(status) > 0:
        return 1
    return 2


apply_theme(DEFAULT_THEME)
