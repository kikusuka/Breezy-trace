import os
import subprocess
from datetime import date, datetime
from pathlib import Path

from breezy_trace import metrics, theme, visuals
from breezy_trace.metrics import collect_repo_metrics, lobby_metrics


def test_parse_commit_log_reads_local_author_time_and_skips_garbage() -> None:
    commits = metrics.parse_commit_log(
        "2026-11-06T23:10:00+05:30\tKiku\nnot a date\tX\n2026-11-02T08:00:00+00:00\t\n"
    )
    assert [(c[0].hour, c[1]) for c in commits] == [(23, "Kiku"), (8, "unknown")]
    weekday, hours = metrics.rhythm(commits)
    assert weekday[datetime(2026, 11, 6).weekday()] == 1 and hours[23] == 1


def test_streaks_allow_a_quiet_today_without_breaking_the_run() -> None:
    assert metrics.streaks([0, 1, 1, 0, 1, 1, 1]) == (3, 3)
    assert metrics.streaks([1, 1, 1, 0]) == (3, 3)  # today not over yet
    assert metrics.streaks([1, 1, 0, 0]) == (0, 2)
    assert metrics.streaks([]) == (0, 0)


def test_numstat_totals_ignore_binary_lines_but_count_the_file() -> None:
    added, deleted, files = metrics.parse_numstat("10\t2\ta.py\n-\t-\timg.png\n5\t0\ta.py\nbad\n")
    assert (added, deleted, files) == (15, 2, 2)


def test_language_breakdown_ignores_unknown_types() -> None:
    result = metrics.language_breakdown(
        [("a.py", 300), ("b.py", 100), ("c.kt", 200), ("pic.png", 9999), ("Makefile", 5)]
    )
    assert result == [("Python", 400), ("Kotlin", 200)]


def test_age_and_relative_days_wording() -> None:
    today = date(2026, 11, 7)
    assert metrics.describe_age(date(2026, 11, 1), today) == "6d"
    assert metrics.describe_age(date(2026, 5, 7), today) == "6mo"
    assert metrics.describe_age(date(2024, 5, 7), today) == "2y 6mo"
    assert [metrics.relative_days(n) for n in (0, 1, 5)] == ["today", "yesterday", "5 days ago"]


def test_stacked_cells_always_fill_the_width() -> None:
    cells = visuals.stacked_cells([62, 28, 10], 40)
    assert sum(cells) == 40 and cells[0] > cells[1] > cells[2]
    assert visuals.stacked_cells([0, 0], 10) == [0, 0]


def test_lobby_metrics_summarise_all_projects() -> None:
    today = date(2026, 11, 7)  # a Saturday
    busy = [0] * 70 + [1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2]
    quiet = [3] + [0] * 83
    result = lobby_metrics({"a": busy, "b": quiet}, {"a": "busy", "b": "quiet"}, today)
    assert result is not None
    assert result.commits_7d == 14 and result.commits_prev_7d == 7
    assert result.trend == 1.0
    assert result.active_projects == 1 and result.tracked_projects == 2
    assert result.streak == 14
    assert result.stalest == ("quiet", 83)
    assert lobby_metrics({}, {}, today) is None


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Kiku",
        "GIT_AUTHOR_EMAIL": "k@example.com",
        "GIT_COMMITTER_NAME": "Kiku",
        "GIT_COMMITTER_EMAIL": "k@example.com",
    }
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    )


def test_collect_repo_metrics_on_a_real_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "app.py").write_text("print('a')\nprint('b')\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "first")
    (repo / "app.py").write_text("print('a')\nprint('b')\nprint('c')\n", encoding="utf-8")
    (repo / "notes.md").write_text("# hi\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "second")
    _git(repo, "tag", "v1")

    result = collect_repo_metrics(repo)
    assert result is not None
    assert result.total_commits == 2 and result.commits_7d == 2 and result.commits_84d == 2
    assert result.streak_current == 1 and result.active_days_30 == 1
    assert result.first_commit == date.today() and result.last_commit is not None
    assert result.tracked_files == 2 and result.tracked_bytes > 0
    assert result.tags == 1 and result.heads == 1
    assert result.contributors == 1 and result.authors == [("Kiku", 2)]
    assert result.lines_added >= 4 and result.files_touched == 2
    assert {name for name, _ in result.languages} == {"Python", "Markdown"}
    assert result.hot[0] == ("app.py", 2)
    assert sum(result.weekday) == 2 and sum(result.hours) == 2


def test_collect_repo_metrics_handles_empty_and_missing_repositories(tmp_path: Path) -> None:
    assert collect_repo_metrics(tmp_path / "missing") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init")
    result = collect_repo_metrics(empty)
    assert result is not None and result.total_commits == 0 and result.last_commit is None


def test_themes_switch_in_place_and_stay_blue_family() -> None:
    try:
        assert theme.apply_theme("sky") == "sky"
        assert theme.is_light_theme() and theme.PALETTE["bg"] == "#3E9FD8"
        light_heat = list(theme.HEAT)
        assert theme.apply_theme("midnight") == "midnight"
        assert not theme.is_light_theme() and theme.PALETTE["bg"] == "#04122E"
        assert list(theme.HEAT) != light_heat and len(theme.HEAT) == 5
        assert theme.next_theme("sky") == "midnight" and theme.next_theme("midnight") == "sky"
        assert theme.apply_theme("nonsense") == theme.DEFAULT_THEME
    finally:
        theme.apply_theme(theme.DEFAULT_THEME)
    assert set(theme.THEMES["sky"]["palette"]) == set(theme.THEMES["midnight"]["palette"])


def test_describe_elapsed_and_parse_since() -> None:
    from datetime import timedelta

    assert metrics.describe_elapsed(timedelta(seconds=20)) == "just now"
    assert metrics.describe_elapsed(timedelta(minutes=5)) == "5 min ago"
    assert metrics.describe_elapsed(timedelta(hours=1)) == "1 hour ago"
    assert metrics.describe_elapsed(timedelta(days=1, hours=2)) == "yesterday"
    assert metrics.describe_elapsed(timedelta(days=9)) == "9 days ago"
    assert metrics.describe_elapsed(timedelta(days=95)) == "3 months ago"
    assert metrics.parse_since(None) is None and metrics.parse_since("nonsense") is None
    naive = metrics.parse_since("2026-11-06T10:00:00")
    assert naive is not None and naive.utcoffset() is not None


def test_since_digest_counts_only_new_work(tmp_path: Path) -> None:
    from datetime import UTC, timedelta

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "one")
    (repo / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "two")

    now = datetime.now(UTC)
    digest = metrics.since_digest(repo, now - timedelta(hours=1))
    assert digest is not None
    assert digest.total_commits == 2 and digest.authors == 1
    assert [subject for _sha, _who, subject in digest.commits] == ["two", "one"]
    assert digest.added == 2 and digest.deleted == 0 and digest.files == 1
    later = metrics.since_digest(repo, now + timedelta(hours=1))
    assert later is not None and later.total_commits == 0
    assert metrics.since_digest(tmp_path / "missing", now) is None


def test_todo_parsing_and_scan(tmp_path: Path) -> None:
    total, shown = metrics.parse_todos(
        "a.py:3:    # TODO: fix this\nb.py:10:FIXME   later\nbroken line\nc.py:x:no\n", limit=1
    )
    assert total == 2 and shown == [("a.py", 3, "# TODO: fix this")]

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "a.py").write_text("# TODO: one\nok = 1\n# FIXME: two\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "x")
    result = collect_repo_metrics(repo)
    assert result is not None and result.todo_total == 2
    assert result.todos[0][:2] == ("a.py", 1)
