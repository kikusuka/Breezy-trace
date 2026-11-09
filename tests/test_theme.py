from breezy_trace import theme, visuals
from breezy_trace.models import GitStatus


def _status(**overrides) -> GitStatus:
    values = {
        "branch": "main", "staged": 0, "modified": 0, "untracked": 0,
        "ahead": 0, "behind": 0, "clean": True, "summary": "",
    }
    values.update(overrides)
    return GitStatus(**values)


def test_clean_repository_is_green_check() -> None:
    status = _status()
    assert theme.state_segments(status) == [(visuals.CHECK, theme.PALETTE["clean"])]
    assert theme.state_color(status) == theme.PALETTE["clean"]
    assert not theme.needs_attention(status)


def test_segments_report_changes_ahead_and_behind() -> None:
    status = _status(modified=2, untracked=1, ahead=3, behind=1, clean=False)
    assert [piece for piece, _ in theme.state_segments(status)] == ["±3", "↑3", "↓1"]
    assert theme.attention_reasons(status) == ["3 uncommitted", "3 unpushed", "1 behind"]


def test_state_colour_prefers_most_urgent_state() -> None:
    assert theme.state_color(_status(behind=1, modified=5)) == theme.PALETTE["danger"]
    assert theme.state_color(_status(modified=1)) == theme.PALETTE["dirty"]
    assert theme.state_color(_status(ahead=2)) == theme.PALETTE["ahead"]


def test_unavailable_repository_never_needs_attention() -> None:
    status = GitStatus.unavailable("git missing")
    assert theme.is_unavailable(status)
    assert not theme.needs_attention(status)
    assert theme.state_segments(status) == [("?", theme.PALETTE["faint"])]


def test_attention_rank_orders_behind_then_dirty_then_unpushed() -> None:
    assert (
        theme.attention_rank(_status(behind=1))
        < theme.attention_rank(_status(modified=1))
        < theme.attention_rank(_status(ahead=1))
    )


def test_css_variables_use_tr_prefix() -> None:
    variables = theme.css_variables()
    assert variables["tr-primary"] == theme.PALETTE["primary"]
    assert set(variables) == {f"tr-{name}" for name in theme.PALETTE}
