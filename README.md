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
python -m pip install -e ".[dev,code]"
```

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`.

Multi-language indexing is optional. From this checkout, install `python -m pip install -e ".[code]"` to enable Tree-sitter support. The first explicit index of a language may download that language's grammar into the local cache; source files are never uploaded.

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
| `breezy-trace inspect` | Show staged/unstaged diff summaries, merge conflicts, and stash count |
| `breezy-trace branches` (or `breezy-trace git`) | Show local branches, upstream divergence, cached remote branches, and commit differences |
| `breezy-trace sessions --sync` | Discover and index local Claude Code and OpenCode session metadata |
| `breezy-trace sessions` | List previously indexed agent sessions |
| `breezy-trace activity scan` | Explicitly snapshot changed Git paths without reading file contents |
| `breezy-trace activity log` | Show recorded file-state transitions |
| `breezy-trace code languages` | List built-in and optional parser support |
| `breezy-trace code index` | Explicitly index supported language symbols and imports |
| `breezy-trace code search <query>` | Search indexed symbols across supported languages |
| `breezy-trace code imports [query]` | Search indexed imports across supported languages |\n| `breezy-trace code calls [query]` | Inspect syntactic Python call sites (targets are not resolved) |
| `breezy-trace backup` | Create a consistent portable SQLite backup |
| `breezy-trace backup --output ./trace-backup.sqlite3` | Choose a backup destination |
| `breezy-trace restore ./trace-backup.sqlite3 --yes` | Restore local data after explicit confirmation |
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

The application database is stored in the operating system's per-user application data directory (resolved with `platformdirs`). SQLite uses foreign keys and WAL mode. Project registration and journal records are local to that database; your Git repository is not modified. Use `breezy-trace backup` before moving machines or making risky changes. Restore validates the SQLite integrity and Breezy Trace schema before replacing the database; always close other Breezy Trace processes first. Restore requires the explicit `--yes` flag.

Unregistering a project removes its registry record and associated journal data through SQLite foreign-key cascading. Back up the application data directory before manually changing or deleting it.

## Development and validation

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m build
python -m twine check dist/*
```

For a reproducible cold/incremental indexing benchmark against a synthetic repository:

```bash
python scripts/benchmark_index.py --files 1000
```

See [RELEASING.md](RELEASING.md) for the full pre-release and publishing checklist.

## Current scope

The current release candidate includes project registration, a terminal dashboard, notes/tasks/decisions, Git working-tree status, staged and unstaged diff summaries, conflict and stash counts, local branch and upstream intelligence, cached remote-tracking branches, local-only/upstream-only commit summaries, recent local commit history, a resume summary, and portable SQLite backup/restore. Claude Code and OpenCode metadata-only session discovery is available through `breezy-trace sessions --sync`. Breezy Trace reads Claude Code `sessions-index.json` and OpenCode session metadata JSON only; it does not read transcript/message stores or persist prompt text, summaries, or session titles. Cursor, Windsurf, VS Code, Zed, file-activity-to-agent correlation, remote-provider APIs, and call graphs and agent-to-file attribution are not implemented yet and are not claimed as available. File activity currently requires an explicit `activity scan`; it records Git-reported paths and status transitions only, does not capture or store file contents (Git may inspect files while calculating status), and does not run a background watcher. Code intelligence currently requires an explicit `code index`; Python parsing is built in, while JavaScript, TypeScript/TSX, Rust, Go, Java, C#, C/C++, Ruby, and PHP use optional Tree-sitter support. It stores symbol/import metadata and content hashes only, and never stores source text, comments, or docstrings. Tree-sitter grammars are fetched only on the user's explicit indexing action and cached locally; this grammar download is the only network activity involved in multi-language indexing. Git-ignored files, symlinks, and files larger than 1 MB are skipped.

## License

Breezy Trace is released under the MIT License. See [`LICENSE`](LICENSE) for the complete terms.

Copyright (c) 2026 Breezy.
