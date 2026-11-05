"""Command-line entry point."""

import argparse
import sys
from pathlib import Path

from breezy_trace import __version__\nfrom breezy_trace.backup import backup_database, restore_database\nfrom breezy_trace.config import database_path, data_dir
from breezy_trace.app import TraceApp
from breezy_trace.git import inspect_status, recent_commits
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
    commands.add_parser("home", help="Open the global project dashboard.")\n\n    backup = commands.add_parser("backup", help="Create a portable backup of local project data.")\n    backup.add_argument("--output", type=Path, help="Backup file path (defaults to app data directory).")\n\n    restore = commands.add_parser("restore", help="Restore project data from a backup.")\n    restore.add_argument("backup", type=Path, help="Path to a Breezy Trace .sqlite3 backup.")\n    restore.add_argument("--yes", action="store_true", help="Confirm replacing the current local database.")
    commands.add_parser("status", help="Show read-only Git status for the current project.")
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

    if args.command in {"note", "task", "tasks", "done", "journal", "decision"}:
        project = _current_project(parser, registry)
        store = JournalStore(registry.db_path)
        try:
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
        except ValueError as error:
            parser.error(str(error))
        return

    if args.command == "backup":\n        target = args.output or (data_dir() / f"breezy-trace-backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.sqlite3")\n        try:\n            backup_database(database_path(), target)\n        except (OSError, ValueError, RuntimeError) as error:\n            parser.error(str(error))\n        print(f"Backup created: {target.resolve()}")\n        return\n\n    if args.command == "restore":\n        if not args.yes:\n            parser.error("Restore replaces the current local database. Re-run with --yes after making a backup.")\n        try:\n            restore_database(args.backup, database_path())\n        except (OSError, ValueError, RuntimeError) as error:\n            parser.error(str(error))\n        print("Project data restored. Restart Breezy Trace before continuing.")\n        return\n\n    if args.command == "register":
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

    if args.command in {"status", "resume"}:
        project = _current_project(parser, registry)
        if args.command == "status":
            status = inspect_status(Path(project.path))
            print(f"{project.name} — {status.branch}")
            print(status.summary)
            print(f"Ahead: {status.ahead}  Behind: {status.behind}")
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
