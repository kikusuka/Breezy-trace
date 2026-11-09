"""Deterministic repository and portfolio metrics, read-only and local.

Everything here comes from Git history and the files Git tracks. Nothing is inferred,
estimated or sent anywhere. Parsing helpers are pure so they can be tested directly.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from breezy_trace.git import hot_files, run_git
from breezy_trace.visuals import bucket_days, rebucket

HISTORY_DAYS = 84
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_STAT_FILES = 20000

LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".kt": "Kotlin", ".kts": "Kotlin",
    ".java": "Java",
    ".c": "C", ".h": "C",
    ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".dart": "Dart",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "CSS",
    ".sh": "Shell", ".bat": "Shell", ".ps1": "Shell",
    ".sql": "SQL",
    ".md": "Markdown",
}


@dataclass
class RepoMetrics:
    total_commits: int = 0
    first_commit: date | None = None
    last_commit: datetime | None = None
    tracked_files: int = 0
    tracked_bytes: int = 0
    heads: int = 0
    remotes: int = 0
    tags: int = 0
    daily: list[int] = field(default_factory=list)
    weekly: list[int] = field(default_factory=list)
    commits_7d: int = 0
    commits_30d: int = 0
    commits_84d: int = 0
    active_days_30: int = 0
    streak_current: int = 0
    streak_longest: int = 0
    contributors: int = 0
    authors: list[tuple[str, int]] = field(default_factory=list)
    weekday: list[int] = field(default_factory=lambda: [0] * 7)
    hours: list[int] = field(default_factory=lambda: [0] * 24)
    lines_added: int = 0
    lines_deleted: int = 0
    files_touched: int = 0
    languages: list[tuple[str, int]] = field(default_factory=list)
    hot: list[tuple[str, int]] = field(default_factory=list)
    todo_total: int = 0
    todos: list[tuple[str, int, str]] = field(default_factory=list)


@dataclass
class SinceDigest:
    """What changed in Git since the project was last opened."""

    since: datetime
    total_commits: int
    authors: int
    commits: list[tuple[str, str, str]]  # (short sha, author, subject), newest first
    added: int
    deleted: int
    files: int


# ------------------------------------------------------------------ pure helpers


def parse_since(value: str | None) -> datetime | None:
    """Parse a stored ISO timestamp (naive values are treated as UTC)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def describe_elapsed(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 60:
        return f"{days} days ago"
    return f"{days // 30} months ago"


def parse_todos(stdout: str, limit: int = 8) -> tuple[int, list[tuple[str, int, str]]]:
    """Parse ``git grep -n`` output into ``(total, first ``limit`` (path, line, text))``."""
    found: list[tuple[str, int, str]] = []
    for raw in stdout.splitlines():
        parts = raw.split(":", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            continue
        found.append((parts[0], int(parts[1]), " ".join(parts[2].split())[:100]))
    return len(found), found[:limit]


def parse_commit_log(stdout: str) -> list[tuple[datetime, str]]:
    """Parse ``%aI<TAB>%an`` lines into ``(author datetime, author name)``."""
    commits: list[tuple[datetime, str]] = []
    for line in stdout.splitlines():
        stamp, _, author = line.partition("\t")
        try:
            when = datetime.fromisoformat(stamp.strip())
        except ValueError:
            continue
        commits.append((when, author.strip() or "unknown"))
    return commits


def streaks(daily: list[int]) -> tuple[int, int]:
    """``(current, longest)`` runs of days with commits. A quiet *today* does not break
    the current streak yet, since the day is not over."""
    longest = run = 0
    for value in daily:
        run = run + 1 if value > 0 else 0
        longest = max(longest, run)
    current = 0
    index = len(daily) - 1
    if index >= 0 and daily[index] == 0:
        index -= 1
    while index >= 0 and daily[index] > 0:
        current += 1
        index -= 1
    return current, longest


def rhythm(commits: Iterable[tuple[datetime, str]]) -> tuple[list[int], list[int]]:
    """Commits by weekday (Mon=0) and by hour of day, in the author's local time."""
    weekday = [0] * 7
    hours = [0] * 24
    for when, _author in commits:
        weekday[when.weekday()] += 1
        hours[when.hour] += 1
    return weekday, hours


def parse_numstat(stdout: str) -> tuple[int, int, int]:
    """``(added, deleted, files touched)`` from ``git log --numstat`` output."""
    added = deleted = 0
    files: set[str] = set()
    for line in stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        plus, minus, name = parts
        if plus == "-" or minus == "-":  # binary file
            files.add(name)
            continue
        try:
            added += int(plus)
            deleted += int(minus)
        except ValueError:
            continue
        files.add(name)
    return added, deleted, len(files)


def language_breakdown(files: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    """Bytes per recognised language, largest first. Unknown file types are ignored."""
    totals: Counter[str] = Counter()
    for name, size in files:
        language = LANGUAGE_BY_EXTENSION.get(Path(name).suffix.lower())
        if language:
            totals[language] += size
    return totals.most_common()


def describe_age(first: date, today: date) -> str:
    days = max(0, (today - first).days)
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}mo"
    years, rest = divmod(months, 12)
    return f"{years}y {rest}mo" if rest else f"{years}y"


def relative_days(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


# ------------------------------------------------------------------ git collection


def _stdout(command) -> str:
    return command.stdout if command is not None and command.returncode == 0 else ""


def collect_repo_metrics(path: Path, today: date | None = None) -> RepoMetrics | None:
    """Gather metrics for one repository; ``None`` when Git or the repository is unavailable."""
    today = today or date.today()
    probe = run_git(path, "rev-parse", "--is-inside-work-tree")
    if probe is None or probe.returncode != 0:
        return None

    metrics = RepoMetrics()
    try:
        metrics.total_commits = int(_stdout(run_git(path, "rev-list", "--count", "HEAD")).strip() or 0)
    except ValueError:
        metrics.total_commits = 0

    commits = parse_commit_log(
        _stdout(
            run_git(
                path, "log", "--branches", "--remotes", f"--since={HISTORY_DAYS} days ago",
                "-n", "5000", "--format=%aI%x09%an", timeout=8,
            )
        )
    )
    counts = Counter(when.date() for when, _ in commits)
    metrics.daily = bucket_days(dict(counts), HISTORY_DAYS, today)
    metrics.weekly = rebucket(metrics.daily, 7)
    metrics.commits_7d = sum(metrics.daily[-7:])
    metrics.commits_30d = sum(metrics.daily[-30:])
    metrics.commits_84d = sum(metrics.daily)
    metrics.active_days_30 = sum(1 for value in metrics.daily[-30:] if value > 0)
    metrics.streak_current, metrics.streak_longest = streaks(metrics.daily)
    metrics.weekday, metrics.hours = rhythm(commits)
    authors = Counter(author for _when, author in commits)
    metrics.contributors = len(authors)
    metrics.authors = authors.most_common(5)

    last = parse_commit_log(_stdout(run_git(path, "log", "-1", "--format=%aI%x09x", "HEAD")))
    metrics.last_commit = last[0][0] if last else None
    roots = parse_commit_log(
        _stdout(run_git(path, "log", "--max-parents=0", "--format=%aI%x09x", "HEAD"))
    )
    metrics.first_commit = min((when for when, _ in roots), default=None).date() if roots else None

    added, deleted, touched = parse_numstat(
        _stdout(
            run_git(
                path, "log", "--branches", "--remotes", "--since=30 days ago",
                "--numstat", "--format=", timeout=10,
            )
        )
    )
    metrics.lines_added, metrics.lines_deleted, metrics.files_touched = added, deleted, touched

    names = [name for name in _stdout(run_git(path, "ls-files", "-z", timeout=10)).split("\0") if name]
    sized: list[tuple[str, int]] = []
    for name in names[:MAX_STAT_FILES]:
        try:
            sized.append((name, (path / name).stat().st_size))
        except OSError:
            continue
    metrics.tracked_files = len(names)
    metrics.tracked_bytes = sum(size for _name, size in sized)
    metrics.languages = language_breakdown(sized)

    refs = _stdout(run_git(path, "for-each-ref", "--format=%(refname)")).splitlines()
    metrics.heads = sum(ref.startswith("refs/heads/") for ref in refs)
    metrics.remotes = sum(
        ref.startswith("refs/remotes/") and not ref.endswith("/HEAD") for ref in refs
    )
    metrics.tags = sum(ref.startswith("refs/tags/") for ref in refs)
    metrics.hot = hot_files(path, days=30, limit=8)
    todo_scan = run_git(path, "grep", "-n", "-I", "-E", "TODO|FIXME", timeout=8)
    if todo_scan is not None and todo_scan.returncode == 0:
        metrics.todo_total, metrics.todos = parse_todos(todo_scan.stdout)
    return metrics


def find_todos(path: Path, limit: int = 500) -> list[tuple[str, int, str]]:
    """Every TODO/FIXME comment in tracked files as ``(path, line, text)``."""
    scan = run_git(path, "grep", "-n", "-I", "-E", "TODO|FIXME", timeout=10)
    if scan is None or scan.returncode != 0:
        return []
    return parse_todos(scan.stdout, limit=limit)[1]


def since_digest(path: Path, since: datetime) -> SinceDigest | None:
    """Commits and line changes on local branches and remotes since ``since``."""
    stamp = since.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S +0000")
    log = run_git(
        path, "log", "--branches", "--remotes", f"--since={stamp}", "-n", "500",
        "--format=%h%x09%an%x09%s", timeout=8,
    )
    if log is None or log.returncode != 0:
        return None
    rows = [line.split("\t", 2) for line in log.stdout.splitlines() if line.count("\t") >= 2]
    stats = run_git(
        path, "log", "--branches", "--remotes", f"--since={stamp}", "-n", "500",
        "--numstat", "--format=", timeout=8,
    )
    added, deleted, files = parse_numstat(_stdout(stats))
    return SinceDigest(
        since=since,
        total_commits=len(rows),
        authors=len({row[1] for row in rows}),
        commits=[(row[0], row[1], row[2]) for row in rows[:6]],
        added=added,
        deleted=deleted,
        files=files,
    )


# ------------------------------------------------------------------ lobby aggregate


@dataclass
class LobbyMetrics:
    commits_7d: int
    commits_prev_7d: int
    trend: float | None
    commits_30d: int
    active_projects: int
    tracked_projects: int
    streak: int
    best_weekday: int | None
    stalest: tuple[str, int] | None
    daily_total: list[int]


def lobby_metrics(
    histories: dict[str, list[int]], names: dict[str, str], today: date
) -> LobbyMetrics | None:
    """Portfolio-wide figures from per-project daily commit counts (no extra Git calls)."""
    if not histories:
        return None
    length = max(len(values) for values in histories.values())
    total = [0] * length
    for values in histories.values():
        offset = length - len(values)
        for index, value in enumerate(values):
            total[offset + index] += value
    last7, prev7 = sum(total[-7:]), sum(total[-14:-7])
    trend = None if prev7 == 0 else (last7 - prev7) / prev7
    weekday_totals = [0] * 7
    for index, value in enumerate(total):
        weekday_totals[(today - timedelta(days=length - 1 - index)).weekday()] += value
    best = max(range(7), key=lambda i: weekday_totals[i]) if any(weekday_totals) else None
    stalest: tuple[str, int] | None = None
    for project_id, values in histories.items():
        last_active = max((i for i, v in enumerate(values) if v > 0), default=None)
        quiet = len(values) if last_active is None else len(values) - 1 - last_active
        name = names.get(project_id, project_id)
        if stalest is None or quiet > stalest[1]:
            stalest = (name, quiet)
    return LobbyMetrics(
        commits_7d=last7,
        commits_prev_7d=prev7,
        trend=trend,
        commits_30d=sum(total[-30:]),
        active_projects=sum(1 for values in histories.values() if sum(values[-7:]) > 0),
        tracked_projects=len(histories),
        streak=streaks(total)[0],
        best_weekday=best,
        stalest=stalest,
        daily_total=total,
    )
