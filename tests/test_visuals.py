from datetime import date

import pytest

from breezy_trace import visuals


def test_sparkline_scales_to_peak_and_keeps_zero_lowest() -> None:
    assert visuals.sparkline([]) == ""
    assert visuals.sparkline([0, 0, 0], basic=False) == "▁▁▁"
    line = visuals.sparkline([0, 1, 10], basic=False)
    assert line[0] == "▁" and line[2] == "█" and line[1] not in "▁█"


def test_sparkline_basic_glyphs_use_characters_every_console_font_has() -> None:
    line = visuals.sparkline([0, 1, 5, 10], basic=True)
    assert line[0] == "·" and line[-1] == "█"
    assert set(line) <= set(visuals.SPARK_BASIC)
    assert visuals.sparkline([0, 0], basic=True) == "··"
    assert visuals.CHECK in ("✓", "√") and len(visuals.SPINNER) >= 4


def test_heat_level_ranges() -> None:
    assert visuals.heat_level(0, 10) == 0
    assert visuals.heat_level(1, 100) == 1
    assert visuals.heat_level(10, 10) == 4
    assert visuals.heat_level(5, 0) == 0


def test_bar_has_minimum_one_cell_for_activity() -> None:
    assert visuals.bar(0, 10, 8) == ""
    assert visuals.bar(1, 100, 8) == "█"
    assert visuals.bar(10, 10, 8) == "█" * 8


def test_bucket_days_orders_oldest_first() -> None:
    today = date(2026, 11, 7)
    counts = {date(2026, 11, 7): 3, date(2026, 11, 5): 1}
    assert visuals.bucket_days(counts, 4, today) == [0, 1, 0, 3]


def test_rebucket_aligns_to_newest_values() -> None:
    assert visuals.rebucket([1, 1, 1, 1, 1, 1, 1], 3) == [3, 3]
    assert visuals.rebucket(list(range(84)), 7).__len__() == 12
    with pytest.raises(ValueError):
        visuals.rebucket([1], 0)


def test_reveal_text_types_out() -> None:
    assert visuals.reveal_text("TRACE", 12, 10) == "TR"
    assert visuals.reveal_text("TRACE", 50, 10) == "TRACE"
    assert visuals.reveal_text("TRACE", 3, 10) == ""


def test_logo_scans_in_from_the_left_and_settles() -> None:
    assert len(visuals.LOGO_ROWS) == 5
    assert {len(row) for row in visuals.LOGO_ROWS} == {visuals.LOGO_WIDTH}
    start = visuals.logo_frame(0)
    assert {kind for row in start for _, kind in row} <= {"hidden", "flash"}
    done = visuals.logo_frame(40)
    kinds = {kind for row in done for char, kind in row if char != " "}
    assert kinds == {"settled"}
    mid = visuals.logo_frame(6)
    assert any(kind == "flash" for row in mid for _, kind in row)
    assert any(kind == "hidden" and char == " " for row in mid for char, kind in row)


def test_trace_path_draws_progressively_with_indexed_nodes() -> None:
    assert all(char == " " for char, _ in visuals.trace_path(0, 30, 4))
    full = visuals.trace_path(99, 30, 4)
    assert len(full) == 30
    assert [index for char, index in full if char == "●"] == [0, 1, 2, 3]
    assert full[0] == ("●", 0) and full[-1] == ("●", 3)
    half = visuals.trace_path(9, 30, 4)
    assert half[-1] == (" ", -1)
