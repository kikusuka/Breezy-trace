# Breezy Trace

**Local-first project memory and development intelligence for your terminal.**

[![CI](https://github.com/kikusuka/Breezy-trace/actions/workflows/ci.yml/badge.svg)](https://github.com/kikusuka/Breezy-trace/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](#current-scope-and-limitations)

Breezy Trace is a local-first developer workspace from **Breezy Labs**. It keeps project registration, Git state, notes, tasks, decisions, and recent local commit history together, so you can return to a repository without reconstructing your context from scratch.

## Why Breezy Trace

- **Local-first:** project metadata and journal entries are stored in a local SQLite database.
- **Git-native:** Git remains the source of truth for repository and commit state.
- **No AI dependency:** core features are deterministic and require no model keys or network access.
- **Honest evidence:** manually recorded context is not presented as automatically detected agent activity.
- **Safe by default:** Breezy Trace reads Git state; it does not commit, pull, push, reset, stash, or discard changes.
- **No telemetry:** the application does not send project data to Breezy Labs.

## Requirements

- Python 3.11 or newer
- Git installed and available on `PATH`
- A terminal that supports Textual

## Install

### From PyPI

```bash
python -m pip install breezy-trace
```

For optional multi-language code indexing:

```bash
python -m pip install "breezy-trace[code]"
```

### From a checkout

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,code]"
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Multi-language indexing is optional. The first explicit index of a language may download that language's grammar into the local cache; source files are never uploaded.

## Quick start

Register a repository once:

```bash
cd ~/code/my-project
breezy-trace register .
```

Then run `breezy-trace` (or `trace` / `btrace`) from that registered repository to open its overview. From an unregistered Git repository, launch either command and confirm the registration prompt. From outside a repository, the command opens the global project selector.

## What you get

| Area | What it does |
| --- | --- |
| Project lobby | Browse registered projects, add an existing folder, create a project, clone a repository, or remove a project from Trace. |
| Resume | Shows notes, open tasks, decisions, Git state, and recent local commits for the current project. |
| Metrics | Commit activity, authors, TODO/FIXME markers, and project metrics. |
| Journal | Notes, tasks, and decisions stored in the local SQLite database. |
| Git | Read-only working-tree status, staged and unstaged diff summaries, conflicts, stash count, branches, upstream state, and cached remote branches. |
| Activity | Explicit snapshots of changed Git paths and file-state transitions, plus metadata-only Claude Code and OpenCode session discovery. |
| Code | Explicit symbol and import indexing for Python and optional Tree-sitter languages, with code search, import search, and syntactic Python call sites. |
| Settings | Theme selection, local data backup, and related preferences. |

## Keyboard shortcuts

### Lobby

| Key | Action |
| --- | --- |
| `o` | Add a repository that already exists on this machine. |
| `n` | Create a brand-new project. |
| `c` | Clone a repository from a GitHub, GitLab, or other Git URL. |
| `Delete` | Remove a project from Trace. Its files are never touched. |
| Arrow keys, `Enter` | Select and open a project. |
| `/` | Search notes, tasks, and decisions across all projects. |
| `?` or `F1` | Open help from anywhere. |

### Inside a project

| Key | Action |
| --- | --- |
| `1`–`7` | Switch between Resume, Metrics, Journal, Git, Activity, Code, and Settings. |
| `Esc` | Return to the lobby. |
| `n` | Add a note. |
| `t` | Add a task. |
| `d` | Record a decision. |
| `x` | Complete a task. |
| `i` | Index code. |
| `a` | Scan file activity. |
| `s` | Sync agent session metadata. |
| `e` | Export a Markdown handoff. |
| `N` | Write a note in your editor. |
| `m` | Turn TODO/FIXME comments into tasks. |
| `b` | Back up local data. |
| `u` | Show the standup. Press again for 3 and 7 days. |
| `/` | Search across all projects. |
| `r` | Refresh. |
| `T` or `F2` | Switch between the blue and midnight-blue themes. The choice is remembered. |
| `?` or `F1` | Open help. |
| `w` | Open the project's GitHub or GitLab page. |
| `v` | Open the project in your editor, file manager, or terminal. |
| `R` | Run one of the project's own commands (pytest, npm scripts, cargo, go, gradle, make, dotnet). |

On the classic Windows console, thin block characters are replaced with widely available ones automatically. Set `BREEZY_TRACE_GLYPHS=full` or `basic` to override, or use Windows Terminal for the full look. Nested repositories resolve to their own Git root.

## CLI reference

| Command | Purpose |
| --- | --- |
| `breezy-trace` (or `trace` / `btrace`) | Open the current project or global home. |
| `breezy-trace register <path>` | Register a Git repository. |
| `breezy-trace register . --name "Display name"` | Register with a display name. |
| `breezy-trace projects` | List registered projects. |
| `breezy-trace home` | Open the global project selector. |
| `breezy-trace note` (no title) | Write the note in your editor (`$VISUAL` / `$EDITOR`; Notepad on Windows). |
| `breezy-trace todos [--import]` | List TODO/FIXME comments, or turn them into tasks without duplicates. |
| `breezy-trace standup [--days N] [--all-authors]` | Markdown standup: your commits, finished tasks, decisions, and what is next, across all projects. |
| `breezy-trace prompt [--fast] [--unicode]` | A few characters of project state for your shell prompt; silent outside registered repositories. |
| `breezy-trace prompt --init SHELL` | Setup code for `powershell`, `bash`, `zsh`, or `starship`. |
| `breezy-trace open [PATH]` | Open a folder in Breezy Trace, adding it first if needed (offers `git init` for a plain folder). |
| `breezy-trace integrate install` | Windows: add a right-click **Open with Breezy Trace** to Explorer (`uninstall` / `status` too). |
| `breezy-trace new NAME [--in DIR]` | Create a new project: a folder with an empty Git repository, registered. |
| `breezy-trace clone URL [--into DIR]` | Clone a GitHub / GitLab / any Git URL and register it (uses the network because you ask). |
| `breezy-trace search QUERY` | Search notes, tasks, and decisions across every project. |
| `breezy-trace handoff [--out FILE]` | Markdown summary to paste into any agent or hand to a teammate. |
| `breezy-trace --no-intro` | Skip the animated boot sequence (or set `BREEZY_TRACE_NO_INTRO=1`). |
| `breezy-trace status` | Show read-only Git status. |
| `breezy-trace inspect` | Show staged/unstaged diff summaries, merge conflicts, and stash count. |
| `breezy-trace branches` (or `breezy-trace git`) | Show local branches, upstream divergence, cached remote branches, and commit differences. |
| `breezy-trace sessions --sync` | Discover and index local Claude Code and OpenCode session metadata. |
| `breezy-trace sessions` | List previously indexed agent sessions. |
| `breezy-trace activity scan` | Explicitly snapshot changed Git paths without reading file contents. |
| `breezy-trace activity log` | Show recorded file-state transitions. |
| `breezy-trace code languages` | List built-in and optional parser support. |
| `breezy-trace code index` | Explicitly index supported language symbols and imports. |
| `breezy-trace code search <query>` | Search indexed symbols across supported languages. |
| `breezy-trace code imports [query]` | Search indexed imports across supported languages. |
| `breezy-trace code calls [query]` | Inspect syntactic Python call sites (targets are not resolved). |
| `breezy-trace backup` | Create a consistent portable SQLite backup. |
| `breezy-trace backup --output ./trace-backup.sqlite3` | Choose a backup destination. |
| `breezy-trace restore ./trace-backup.sqlite3 --yes` | Restore local data after explicit confirmation. |
| `breezy-trace resume` | Show notes, open tasks, decisions, Git state, and recent local commits. |
| `breezy-trace note "Title" --body "..."` | Save project context. |
| `breezy-trace journal` | List recent notes. |
| `breezy-trace task "Title" --details "..."` | Add an open task. |
| `breezy-trace tasks` | List open tasks. |
| `breezy-trace tasks --all` | Include completed tasks. |
| `breezy-trace done <task-id>` | Complete an open task. |
| `breezy-trace decision "Title" "Decision"` | Record a project decision. |
| `breezy-trace unregister <name-or-path>` | Remove a project from the selector. |

Journal commands operate on the registered project containing the current working directory. They do not silently create or register projects.

## Data, privacy, and safety

The application database is stored in the operating system's per-user application data directory (resolved with `platformdirs`). SQLite uses foreign keys and WAL mode. Project registration and journal records are local to that database; your Git repository is not modified. Use `breezy-trace backup` before moving machines or making risky changes. Restore validates the SQLite integrity and Breezy Trace schema before replacing the database; always close other Breezy Trace processes first. Restore requires the explicit `--yes` flag. Set `BREEZY_TRACE_DATA_DIR` to use a separate data folder.

Unregistering a project removes its registry record and associated journal data through SQLite foreign-key cascading. Back up the application data directory before manually changing or deleting it.

Breezy Trace does not run a background watcher, startup fetch, or network call. Network access happens only when you explicitly clone a repository or explicitly index a language whose grammar is not cached locally. Agent integrations read metadata only and never read prompts or transcripts.

## Shell prompt

`breezy-trace prompt` prints something like `cyrrus main *2 ^1 t3` (project, branch, changed files, unpushed commits, open tasks) and nothing at all outside a registered repository, so it is safe in every prompt. It never loads the terminal UI, so it is quick. Add it to your prompt with the generated setup code, for example in PowerShell:

```powershell
breezy-trace prompt --init powershell >> $PROFILE
```

`--fast` prints only the project name and open tasks (one Git call), and `--unicode` uses `± ↑ ↓ ✓ ○` instead of ASCII. The classic `cmd.exe` prompt cannot run commands, so use PowerShell or Windows Terminal.

## Adding projects from Windows Explorer

```bat
breezy-trace integrate install
```

This adds **Open with Breezy Trace** to the right-click menu of folders (Windows 11: under *Show more options*). Choosing it adds the folder if needed and opens it; for a folder that is not a Git repository yet, it asks before creating one. It only writes two per-user registry keys, and `breezy-trace integrate uninstall` removes them. You can also drag a folder from Explorer into the path box of the `o` dialog.

## Development and validation

```bash
python -m pip install -e ".[dev,code]"
ruff format --check .
ruff check .
pytest
python -m build
python -m twine check dist/*
```

For a reproducible cold/incremental indexing benchmark against a synthetic repository:

```bash
python scripts/benchmark_index.py --files 1000
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and [RELEASING.md](RELEASING.md) for the full pre-release and publishing checklist.

## Current scope and limitations

Breezy Trace 0.1.0 includes project registration, a terminal dashboard, notes/tasks/decisions, Git working-tree status, staged and unstaged diff summaries, conflict and stash counts, local branch and upstream intelligence, cached remote-tracking branches, local-only/upstream-only commit summaries, recent local commit history, a resume summary, and portable SQLite backup/restore.

**Agent sessions.** Claude Code and OpenCode metadata-only session discovery is available through `breezy-trace sessions --sync`. Breezy Trace reads Claude Code `sessions-index.json` and OpenCode session metadata JSON only; it does not read transcript/message stores or persist prompt text, summaries, or session titles. Cursor, Windsurf, VS Code, Zed, file-activity-to-agent correlation, remote-provider APIs, resolved call graphs, and agent-to-file attribution are not implemented yet and are not claimed as available.

**Call sites.** The current Python call-site command reports syntactic call expressions only; it does not resolve runtime targets.

**File activity.** File activity currently requires an explicit `activity scan`. It records Git-reported paths and status transitions only, does not capture or store file contents (Git may inspect files while calculating status), and does not run a background watcher. Its event history is automatically bounded to the newest 10,000 events per project and 90 days; current working-tree state is retained separately.

**Code intelligence.** Code intelligence currently requires an explicit `code index`. Python parsing is built in, while JavaScript, TypeScript/TSX, Rust, Go, Java, C#, C/C++, Ruby, and PHP use optional Tree-sitter support. It stores symbol/import metadata and content hashes only, and never stores source text, comments, or docstrings. Tree-sitter grammars are fetched only on the user's explicit indexing action and cached locally; this grammar download is the only network activity involved in multi-language indexing. Git-ignored files, symlinks, and files larger than 1 MB are skipped.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the local setup, checks, and pull-request expectations, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations. For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## License

Breezy Trace is released under the MIT License. See [LICENSE](LICENSE) for the complete terms.

Copyright (c) 2026 Breezy.
