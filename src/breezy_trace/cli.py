"""Command-line entry point."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from breezy_trace import __version__
from breezy_trace.activity import FileActivityStore
from breezy_trace.agents import AgentSessionStore
from breezy_trace.app import TraceApp
from breezy_trace.backup import backup_database, restore_database
from breezy_trace.code_index import PythonCodeIndex
from breezy_trace.polyglot_index import LANGUAGE_EXTENSIONS, TreeSitterCodeIndex
from breezy_trace.config import data_dir, database_path
from breezy_trace.git import branch_intelligence, inspect_details, inspect_status, recent_commits
from breezy_trace.journal import JournalStore
from breezy_trace.registry import ProjectError, ProjectRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="breezy-trace",
        description="Local-first project memory and development intelligence.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    register = commands.add_parser("register", help="Register a local Git project.")
    register.add_argument("path", nargs="?", default=".")
    register.add_argument("--name", help="Optional display name.")

    unregister = commands.add_parser("unregister", help="Unregister a project by name or path.")
    unregister.add_argument("project")

    commands.add_parser("projects", help="List registered projects.")
    commands.add_parser("home", help="Open the global project dashboard.")

    backup = commands.add_parser("backup", help="Create a portable backup of local project data.")
    backup.add_argument("--output", type=Path, help="Backup file path (defaults to app data directory).")

    restore = commands.add_parser("restore", help="Restore project data from a backup.")
    restore.add_argument("backup", type=Path, help="Path to a Breezy Trace .sqlite3 backup.")
    restore.add_argument("--yes", action="store_true", help="Confirm replacing the current local database.")
    commands.add_parser("status", help="Show read-only Git status for the current project.")
    commands.add_parser("inspect", help="Show detailed read-only Git changes, conflicts, and stashes.")
    commands.add_parser("branches", aliases=["git"], help="Show local branches, upstream state, and cached remote commits.")
    commands.add_parser("resume", help="Show the context needed to resume the current project.")

    note = commands.add_parser("note", help="Add a note to the current registered project.")
    note.add_argument("title")
    note.add_argument("--body", default="", help="Note content.")

    task = commands.add_parser("task", help="Add a task to the current registered project.")
    task.add_argument("title")
    task.add_argument("--details", default="", help="Additional task details.")

    tasks = commands.add_parser("tasks", help="List tasks for the current registered project.")
    tasks.add_argument("--all", action="store_true", help="Include completed tasks.")

    done = commands.add_parser("done", help="Mark a project task as complete.")
    done.add_argument("task_id")

    commands.add_parser("journal", help="Show recent notes for the current project.")
    activity = commands.add_parser("activity", help="Scan and review metadata-only file activity.")
    activity_commands = activity.add_subparsers(dest="activity_command", required=True)
    activity_commands.add_parser("scan", help="Take an explicit read-only Git working-tree snapshot.")
    activity_log = activity_commands.add_parser("log", help="Show recorded file activity transitions.")
    activity_log.add_argument("--limit", type=int, default=30, help="Maximum events to show (1-500).")

    code = commands.add_parser("code", help="Index and search source symbols and imports.")
    code_commands = code.add_subparsers(dest="code_command", required=True)
    code_commands.add_parser("index", help="Explicitly index supported languages from Git-listed files.")
    code_search = code_commands.add_parser("search", help="Search indexed symbol names across languages.")
    code_search.add_argument("query")
    code_search.add_argument("--limit", type=int, default=50)
    code_commands.add_parser("languages", help="Show built-in and optional language support.")
    code_imports = code_commands.add_parser("imports", help="List indexed imports, optionally filtered by module.")
    code_imports.add_argument("query", nargs="?")
    code_imports.add_argument("--limit", type=int, default=100)

    sessions = commands.add_parser("sessions", help="List detected coding-agent sessions for this project.")
    sessions.add_argument("--sync", action="store_true", help="Discover local Claude Code and OpenCode session metadata first.")

    decision = commands.add_parser("decision", help="Record a project decision.")
    decision.add_argument("title")
    decision.add_argument("decision")
    decision.add_argument("--context", default="", help="Context behind the decision.")
    return parser


def _current_project(parser: argparse.ArgumentParser, registry: ProjectRegistry):
    project = registry.find_by_path(Path.cwd())
    if project is None:
        parser.error(
            "The current directory is not a registered Git project. "
            "Run: breezy-trace register ."
        )
    return project


def _print_resume(project, registry: ProjectRegistry) -> None:
    status = inspect_status(Path(project.path))
    store = JournalStore(registry.db_path)
    print(f"{project.name} — {project.path}")
    print(f"Branch: {status.branch}")
    print(f"Working tree: {status.summary}")
    print(f"Remote tracking: ahead {status.ahead}, behind {status.behind}")

    tasks = store.list_tasks(project, status="open")
    print(f"\nNEXT TASKS ({len(tasks)})")
    for item in tasks[:10]:
        suffix = f" — {item['details']}" if item["details"] else ""
        print(f"- {item['title']}{suffix}")
    if not tasks:
        print("- No open tasks recorded.")

    notes = store.list_entries(project, limit=5)
    print("\nRECENT NOTES")
    for entry in notes:
        print(f"- {entry['title']}: {entry['body']}" if entry["body"] else f"- {entry['title']}")
    if not notes:
        print("- No notes recorded.")

    decisions = store.list_decisions(project, limit=3)
    print("\nRECENT DECISIONS")
    for item in decisions:
        print(f"- {item['title']}: {item['decision']}")
    if not decisions:
        print("- No decisions recorded.")

    sessions = AgentSessionStore(registry.db_path).list_sessions(project, limit=5)
    print("\nRECENT AGENT SESSIONS")
    for session in sessions:
        print(f"- {session['provider']} {session['external_id']} ({session['started_at'] or 'unknown start'})")
    if not sessions:
        print("- No sessions indexed. Run: breezy-trace sessions --sync")

    commits = recent_commits(Path(project.path), limit=5)
    print("\nRECENT COMMITS (local history)")
    for commit in commits:
        print(f"- {commit['date']} {commit['sha']} {commit['subject']}")
    if not commits:
        print("- No commits available.")


def main() -> None:
    parser = build_parser()
    args, remainder = parser.parse_known_args()
    registry = ProjectRegistry()

    if args.command in {"note", "task", "tasks", "done", "journal", "decision", "sessions", "activity", "code"}:
        project = _current_project(parser, registry)
        store = JournalStore(registry.db_path)
        try:
            if args.command == "code":
                code_index = PythonCodeIndex(registry.db_path)
                if args.code_command == "index":
                    summary = code_index.index(project)
                    print(
                        f"Python: {summary['files_indexed']} indexed, "
                        f"{summary['files_unchanged']} unchanged, "
                        f"{summary['syntax_errors']} syntax errors, "
                        f"{summary['files_skipped']} skipped."
                    )
                    if TreeSitterCodeIndex.available():
                        polyglot = TreeSitterCodeIndex(registry.db_path).index(project)
                        print(
                            f"Tree-sitter: {polyglot['files_indexed']} indexed, "
                            f"{polyglot['files_unchanged']} unchanged, "
                            f"{polyglot['syntax_errors']} syntax errors, "
                            f"{polyglot['files_skipped']} skipped, "
                            f"{polyglot['stale_files_removed']} stale files removed."
                        )
                    else:
                        print(
                            "Other languages not indexed. Install optional support with: "
                            "pip install 'breezy-trace[code]'"
                        )
                elif args.code_command == "languages":
                    print("Built-in: Python")
                    print("Optional Tree-sitter languages:")
                    for language, extensions in LANGUAGE_EXTENSIONS.items():
                        print(f"- {language}: {', '.join(sorted(extensions))}")
                    print(
                        "Tree-sitter package: "
                        + ("installed" if TreeSitterCodeIndex.available() else "not installed")
                    )
                elif args.code_command == "search":
                    results = code_index.search(project, args.query, args.limit)
                    if not results:
                        print("No matching symbols. Run: breezy-trace code index")
                    for item in results:
                        print(
                            f"{item['path']}:{item['line']}  "
                            f"{item['kind']:<16} {item['qualified_name']} [{item.get('language', 'python')}]"
                        )
                elif args.code_command == "imports":
                    results = code_index.imports(project, args.query, args.limit)
                    if not results:
                        print("No matching imports. Run: breezy-trace code index")
                    for item in results:
                        print(
                            f"{item['path']}:{item['line']}  "
                            f"{item['module']} [{item.get('language', 'python')}]"
                        )
                return
            if args.command == "activity":
                activity_store = FileActivityStore(registry.db_path)
                if args.activity_command == "scan":
                    summary = activity_store.scan(project)
                    print(
                        f"Scanned Git working tree: {summary['paths']} changed paths; "
                        f"{summary['events_created']} new activity events."
                    )
                elif args.activity_command == "log":
                    records = activity_store.list_events(project, args.limit)
                    if not records:
                        print("No file activity recorded. Run: breezy-trace activity scan")
                    for record in records:
                        print(f"{record['observed_at']}  {record['event_type']:<20} {record['path']}")
                return
            if args.command == "note":
                store.add_note(project, args.title, args.body)
                print(f"Saved note: {args.title}")
            elif args.command == "task":
                task_id = store.add_task(project, args.title, args.details)
                print(f"Added task: {args.title} ({task_id})")
            elif args.command == "tasks":
                for item in store.list_tasks(project, None if args.all else "open"):
                    marker = "x" if item["status"] == "done" else " "
                    print(f"[{marker}] {item['title']}  ({item['id']})")
            elif args.command == "done":
                if store.complete_task(project, args.task_id):
                    print("Task marked complete.")
                else:
                    print("No open task matched that ID.", file=sys.stderr)
                    raise SystemExit(1)
            elif args.command == "sessions":
                session_store = AgentSessionStore(registry.db_path)
                if args.sync:
                    count = session_store.sync(project)
                    print(f"Scanned local agent indexes; {count} session records inserted or refreshed.")
                records = session_store.list_sessions(project)
                if not records:
                    print("No agent sessions found. Run: breezy-trace sessions --sync")
                for record in records:
                    print(f"- {record['provider']}  {record['external_id']}  {record['started_at'] or 'unknown start'}")
                    metadata = record["metadata"]
                    if metadata.get("git_branch"):
                        print(f"  Branch: {metadata['git_branch']}")
                    if metadata.get("message_count") is not None:
                        print(f"  Messages: {metadata['message_count']}")
            elif args.command == "journal":
                entries = store.list_entries(project)
                if not entries:
                    print('No journal entries yet. Add one with: breezy-trace note "Title"')
                for entry in entries:
                    print(f"{entry['created_at']}  {entry['title']}")
                    if entry["body"]:
                        print(f"  {entry['body']}")
            elif args.command == "decision":
                store.add_decision(project, args.title, args.decision, args.context)
                print(f"Recorded decision: {args.title}")
        except (ValueError, RuntimeError) as error:
            parser.error(str(error))
        return

    if args.command == "backup":
        target = args.output or (data_dir() / f"breezy-trace-backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.sqlite3")
        try:
            backup_database(database_path(), target)
        except (OSError, ValueError, RuntimeError) as error:
            parser.error(str(error))
        print(f"Backup created: {target.resolve()}")
        return

    if args.command == "restore":
        if not args.yes:
            parser.error("Restore replaces the current local database. Re-run with --yes after making a backup.")
        try:
            restore_database(args.backup, database_path())
        except (OSError, ValueError, RuntimeError) as error:
            parser.error(str(error))
        print("Project data restored. Restart Breezy Trace before continuing.")
        return

    if args.command == "register":
        try:
            project = registry.register(Path(args.path), args.name)
        except ProjectError as error:
            parser.error(str(error))
        print(f"Registered {project.name}: {project.path}")
        return

    if args.command == "unregister":
        if registry.unregister(args.project):
            print(f"Unregistered {args.project}")
        else:
            print(f"No registered project matched: {args.project}", file=sys.stderr)
            raise SystemExit(1)
        return

    if args.command == "projects":
        projects = registry.list_projects()
        if not projects:
            print("No projects registered. Run: breezy-trace register <path>")
            return
        for project in projects:
            print(f"{project.name}\n  {project.path}")
        return

    if args.command in {"status", "resume", "inspect", "branches", "git"}:
        project = _current_project(parser, registry)
        if args.command == "status":
            status = inspect_status(Path(project.path))
            print(f"{project.name} — {status.branch}")
            print(status.summary)
            print(f"Ahead: {status.ahead}  Behind: {status.behind}")
        elif args.command in {"branches", "git"}:
            details = branch_intelligence(Path(project.path))
            print(f"{project.name} — Git intelligence")
            print(f"Current branch: {details['current_branch'] or '(detached HEAD)'}")
            print(f"Upstream: {details['upstream'] or 'not configured'}")
            if details["upstream"]:
                print(f"Behind / ahead: {details['behind']} / {details['ahead']}")
            print("\nLOCAL BRANCHES")
            for item in details["local_branches"]:
                marker = " *" if item["name"] == details["current_branch"] else ""
                print(f"- {item['name']} ({item['sha']}){marker}")
            print("\nCACHED REMOTE-TRACKING BRANCHES")
            for item in details["remote_branches"]:
                print(f"- {item['name']} ({item['sha']})")
            print("\nLOCAL COMMITS NOT IN UPSTREAM")
            for item in details["unpushed_commits"]:
                print(f"- {item['sha']} {item['date']} {item['subject']}")
            if not details["unpushed_commits"]:
                print("- None detected (or no upstream configured).")
            print("\nUPSTREAM COMMITS NOT IN LOCAL HEAD")
            for item in details["upstream_only_commits"]:
                print(f"- {item['sha']} {item['date']} {item['subject']}")
            if not details["upstream_only_commits"]:
                print("- None detected (or no upstream configured).")
            print(f"\nStashes: {len(details['stashes'])}")
            print("Remote branch data is from local cached refs; run git fetch yourself to refresh.")
        elif args.command == "inspect":
            status = inspect_status(Path(project.path))
            details = inspect_details(Path(project.path))
            print(f"{project.name} — {status.branch}")
            print(f"Working tree: {status.summary}")
            print(f"Remote tracking: ahead {status.ahead}, behind {status.behind}")
            print(f"Merge conflicts: {details['conflicts']}")
            print(f"Stashes: {details['stashes']}")
            print("\nSTAGED DIFF")
            print(details["staged_diff"] or "No staged changes")
            print("\nUNSTAGED DIFF")
            print(details["unstaged_diff"] or "No unstaged tracked changes")
        else:
            _print_resume(project, registry)
        return

    if remainder:
        if args.command is None and len(remainder) == 1:
            project = registry.find_by_path(Path(remainder[0]))
            if project is None:
                parser.error(
                    f"{remainder[0]} is not a registered Git project. "
                    "Register it first with: breezy-trace register <path>"
                )
            registry.mark_opened(project.id)
            TraceApp(project=project).run()
            return
        parser.error(f"Unrecognized arguments: {' '.join(remainder)}")

    project = None
    if args.command is None:
        project = registry.find_by_path(Path.cwd())
    if project:
        registry.mark_opened(project.id)
    TraceApp(project=project).run()


if __name__ == "__main__":
    main()
