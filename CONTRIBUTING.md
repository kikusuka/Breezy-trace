# Contributing to Breezy Trace

Thanks for helping improve Breezy Trace. This project is a local-first developer tool, so changes should preserve privacy, predictable behavior, and a calm terminal experience.

## Before you start

- Python 3.11 or newer
- Git installed and available on `PATH`
- A terminal that supports Textual

## Set up a development checkout

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,code]"
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Multi-language indexing uses the optional `code` extra. Python indexing works without it.

## Run the checks

```bash
ruff format --check .
ruff check .
pytest
python -m build
python -m twine check dist/*
```

Run `ruff format .` to apply formatting. The full test suite also runs on Windows, macOS, and Linux in CI.

## Code expectations

- Keep Git access read-only. Do not add commands that commit, pull, push, reset, stash, or discard changes.
- Do not add telemetry, analytics, or background network calls.
- Do not read or persist prompts, transcripts, source text, comments, or docstrings from agent or code-index data.
- Prefer standard-library solutions and the existing dependencies.
- Add type hints to public functions.
- Add or update tests for behavior changes.
- Keep user-facing messages clear and honest about what was actually detected.
- Update `CHANGELOG.md` for notable user-visible changes.

## Pull requests

- Keep changes focused and explain the user-visible effect.
- Include the checks you ran.
- Make sure CI is green before requesting review.
- Do not include secrets, tokens, personal data, local databases, build output, or virtual environments.
- Do not force-push a shared branch or rewrite published history.

## Commit messages

Use a short imperative subject, for example:

```text
fix: close registry connections after lookup
docs: explain optional multi-language indexing
```

## Security

Do not report security issues in a public issue. Follow [SECURITY.md](SECURITY.md).
