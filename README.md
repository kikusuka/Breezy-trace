# Breezy Trace

**Project memory and development intelligence for your terminal.**

Breezy Trace is a local-first developer workspace from **Breezy Labs**. It keeps project registration, Git state, notes, tasks, decisions, and recent local commit history together so you can return to a repository without reconstructing your context from scratch.

## Principles

- **Local-first:** project metadata and journal entries are stored in a local SQLite database.
- **Git-native:** Git remains the source of truth for repository and commit state.
- **No AI dependency:** core features are deterministic and require no model keys or network access.
- **Honest evidence:** manually recorded context is not presented as automatically detected agent activity.
- **Safe by default:** Breezy Trace reads Git state; it does not commit, pull, push, reset, stash, or discard changes.
- **No telemetry:** the application does not send project data to Breezy Labs.

## Requirements

- Python 3.11 or newer
- Git installed and available on PATH
- A terminal that supports Textual

## Install from a checkout

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`.

## First run

Register a repository once:

```bash
cd ~/code/my-project
breezy-trace register .
```

Then run `breezy-trace` from that registered repository to open its overview. Run it outside a registered repository to open the global project selector. Only explicitly registered repositories appear in the selector.

## CLI reference

| Command | Purpose |
| --- | --- |
| `breezy-trace` | Open the current registered project or global home |
| `breezy-trace register <path>` | Register a Git repository |
| `breezy-trace register . --name "Display name"` | Register with a display name |
| `breezy-trace projects` | List registered projects |
| `breezy-trace home` | Open the global project selector |
| `breezy-trace status` | Show read-only Git status |
| `breezy-trace resume` | Show notes, open tasks, decisions, Git state, and recent local commits |
| `breezy-trace note "Title" --body "..."` | Save project context |
| `breezy-trace journal` | List recent notes |
| `breezy-trace task "Title" --details "..."` | Add an open task |
| `breezy-trace tasks` | List open tasks |
| `breezy-trace tasks --all` | Include completed tasks |
| `breezy-trace done <task-id>` | Complete an open task |
| `breezy-trace decision "Title" "Decision"` | Record a project decision |
| `breezy-trace unregister <name-or-path>` | Remove a project from the selector |

Journal commands operate on the registered project containing the current working directory. They do not silently create or register projects.

## Data and storage

The application database is stored in the operating system's per-user application data directory (resolved with `platformdirs`). SQLite uses foreign keys and WAL mode. Project registration and journal records are local to that database; your Git repository is not modified.

Unregistering a project removes its registry record and associated journal data through SQLite foreign-key cascading. Back up the application data directory before manually changing or deleting it.

## Development and validation

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m build
python -m twine check dist/*
```

## Current scope

The initial release focuses on reliable project registration, a terminal dashboard, project notes/tasks/decisions, Git working-tree status, recent local commit history, and a resume summary. Coding-agent session integrations, file-activity correlation, remote-provider APIs, and AST indexing are not implemented yet and are not claimed as available.

## License

License selection is pending. No license grant should be assumed until a license is added to this repository.
