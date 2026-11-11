# Changelog

All notable changes to Breezy Trace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the project is pre-1.0, minor versions may include breaking changes.

## [Unreleased]

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
