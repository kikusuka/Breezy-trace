# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## Unreleased

### Fixed
- Breezy Trace no longer treats your home folder, any folder above it, or a filesystem or drive root as a project. Launching inside an unregistered repository now opens the lobby with a hint instead of a blocking registration prompt, and already-registered home-folder entries are flagged for removal.

## [0.2.0] - 2026-11-18

### Added
- One-line installers: `scripts/install.ps1` for Windows PowerShell 5.1 (no administrator rights) and `scripts/install.sh` for macOS and Linux. Both install uv when needed, install Breezy Trace as a uv tool, add the command to `PATH`, verify the install, and are safe to run again.
- `breezy-trace update` upgrades Breezy Trace with the method it was installed with (uv tool, pipx, or plain pip), asks for confirmation unless `--yes` is given, and refuses editable development checkouts with an explanation.
- `breezy-trace update --check` asks the PyPI JSON API once, with a 10-second timeout, whether a newer version exists. It sends no project data and never runs automatically.
- On Windows, `breezy-trace update` finishes the upgrade in a visible console window after the current process exits, writes a log file, and prints the exact manual command if the helper cannot start.
- `install-smoke` CI workflow runs both installers on Ubuntu, macOS, and Windows and checks `breezy-trace --version`.
- CI matrix and package classifiers now include Python 3.14.

### Changed
- README leads with the one-line installers and `uv tool install`, explains why plain `pip install` can leave the command "not found", and uses absolute GitHub links for community files so they work on the PyPI page.
- README privacy section now documents the explicit, single PyPI version check.

---

**Note:** People on 0.1.0 do not have the update command. Please upgrade once with
`uv tool upgrade breezy-trace` (or rerun the installer, or `python -m pip install --upgrade breezy-trace`).

## [0.1.0] - 2026-11-12

The first public release of Breezy Trace.

### Added
- Local project registry backed by SQLite, with per-user data storage.
- Textual terminal workspace with Resume, Metrics, Journal, Git, Activity, Code, and Settings views.
- Notes, tasks, and decisions with search, completion, and Markdown handoff export.
- Read-only Git status, staged and unstaged diff summaries, conflict and stash counts, branch and upstream intelligence, cached remote branches, and recent commit history.
- Resume summary and cross-project standup for recent commits, completed tasks, decisions, and open work.
- Explicit file-activity snapshots that record Git-reported paths and status transitions without storing file contents.
- Metadata-only Claude Code and OpenCode session discovery; prompts and transcripts are never read.
- Built-in Python symbol and import indexing, plus optional Tree-sitter indexing for JavaScript, TypeScript/TSX, Rust, Go, Java, C#, C/C++, Ruby, and PHP.
- Code search, import search, and syntactic Python call-site inspection.
- Portable SQLite backup and validated restore.
- Shell prompt integration for PowerShell, Bash, Zsh, and Starship.
- Windows Explorer **Open with Breezy Trace** integration.
- Project creation, cloning, and opening from the terminal UI and CLI.

### Security
- Git operations are read-only by design; Breezy Trace does not commit, pull, push, reset, stash, or discard changes.
- No telemetry, analytics, or background network calls.
- Agent integrations read metadata only and do not persist prompts, transcripts, or session titles.
- Restore validates the SQLite integrity and Breezy Trace schema before replacing local data.

### Known limitations
- Cursor, Windsurf, VS Code, and Zed integrations are not implemented.
- Resolved call graphs and agent-to-file attribution are not implemented.
- File activity requires an explicit scan and does not run a background watcher.
- Multi-language code indexing requires the optional `breezy-trace[code]` extra.

[Unreleased]: https://github.com/kikusuka/Breezy-trace/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kikusuka/Breezy-trace/releases/tag/v0.1.0