# Breezy Trace

**Project memory and development intelligence for your terminal.**

Breezy Trace is a local-first developer workspace from **Breezy Labs**. It brings project context, Git intelligence, coding-agent activity, notes, and development history into one keyboard-first terminal interface.

## Principles

- **Local-first:** project metadata and notes stay on your machine in SQLite.
- **Git-native:** Git remains the source of truth for version history and repository state.
- **No AI dependency:** the core is deterministic and works without model keys or network access.
- **Honest evidence:** detected facts, user notes, and inferred relationships are kept distinct.
- **Safe by default:** the first release is read-only with respect to Git operations.

## Current foundation

- Textual terminal application with a Breezy Blue visual foundation.
- Global project dashboard and registered-project selector.
- Git-root detection and local project registration.
- SQLite schema for project notes, tasks, decisions, sessions, file events, commits, and remote snapshots.
- Read-only Git working-tree inspection.\n- Project Journal storage for notes, tasks, and recorded decisions.\n- Project overview surfaces recent notes, open tasks, and recent decisions.

## Development

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
breezy-trace register .
breezy-trace
```

Run tests with `pytest`.

## CLI

```bash
breezy-trace                 # Open the dashboard (or the registered current project)
breezy-trace register .      # Register the current Git repository
breezy-trace projects        # List registered projects
breezy-trace unregister NAME # Remove a project from the registry
breezy-trace home            # Open the global dashboard
```

## License

License selection is pending.
