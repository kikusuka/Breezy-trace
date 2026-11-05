# Breezy Trace

**Project memory and development intelligence for your terminal.**

Breezy Trace is a local-first developer workspace from **Breezy Labs**. It brings project context, Git intelligence, coding-agent activity, notes, and development history into one keyboard-first terminal interface.

## Principles

- **Local-first:** project metadata and notes stay on your machine in SQLite.
- **Git-native:** Git remains the source of truth for version history and repository state.
- **No AI dependency:** the core is deterministic and works without model keys or network access.
- **Honest evidence:** detected facts, user notes, and inferred relationships are kept distinct.
- **Safe by default:** the first release is read-only with respect to Git operations.

## Status

Early foundation work. Interfaces and storage are being built before deeper agent and code intelligence integrations.

## Development

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
breezy-trace
```

## License

License selection is pending.
