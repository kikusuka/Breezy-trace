"""Command-line entry point."""

import argparse
import sys
from pathlib import Path

from breezy_trace import __version__
from breezy_trace.app import TraceApp
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
    return parser


def main() -> None:
    parser = build_parser()
    args, remainder = parser.parse_known_args()
    registry = ProjectRegistry()

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

    if remainder:
        parser.error(f"Unrecognized arguments: {' '.join(remainder)}")

    project = None
    if args.command is None:
        project = registry.find_by_path(Path.cwd())
    if project:
        registry.mark_opened(project.id)
    TraceApp(project=project).run()


if __name__ == "__main__":
    main()
