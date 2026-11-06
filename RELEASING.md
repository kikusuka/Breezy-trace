# Breezy Trace release checklist

Use this checklist for every tagged release. Do not publish from an unreviewed branch.

## Before creating a release

- [ ] Review the complete pull request diff and confirm the release version.
- [ ] Confirm the 3 operating systems × 3 Python versions CI matrix is green.
- [ ] Confirm the dependency audit workflow is green.
- [ ] Run `ruff check .` and `pytest` locally.
- [ ] Build both distributions with `python -m build`.
- [ ] Validate distributions with `python -m twine check dist/*`.
- [ ] Install the wheel into a clean virtual environment and smoke-test:
  - [ ] `breezy-trace --help`
  - [ ] `btrace --help`
  - [ ] `python -m breezy_trace --help`
- [ ] Test a fresh database and upgrades from every supported previous schema version.
- [ ] Create a backup containing committed WAL data and restore it into a separate database.
- [ ] Verify a failed restore leaves the existing destination untouched.
- [ ] Run the synthetic indexing benchmark and record cold/incremental timings.
- [ ] Manually open the TUI in a narrow terminal and a normal desktop terminal.
- [ ] Verify project switching, journal, Git, activity, agent metadata and code views.
- [ ] Confirm Git remains read-only and no startup fetch/network operation occurs.
- [ ] Confirm agent integrations still read metadata only, never prompts or transcripts.
- [ ] Confirm no source text, comments or docstrings are persisted by code indexing.
- [ ] Review dependency changes and the generated wheel contents.

## Publishing

- [ ] Confirm the PyPI Trusted Publisher is configured for this repository and workflow.
- [ ] Create a GitHub release with a matching version tag only after approval.
- [ ] Confirm the publish workflow succeeds and the package is installable from PyPI.
- [ ] Verify the published version and release notes.

## Release boundaries

- Never publish directly from a feature or hardening branch.
- Never bypass a failed CI, security audit, build, or wheel-install check.
- Never claim support for an OS/Python combination that has not passed CI.
- Do not create a release or publish to PyPI without explicit release approval.
