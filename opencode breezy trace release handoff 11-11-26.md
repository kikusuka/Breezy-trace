# Breezy Trace — First Release Handoff (11/11/26)

## Status: do not push the current branch as-is

The local project history was created fresh on 11/11/26. GitHub already has a `main` branch and many existing branches. The local branch and GitHub `main` have **no shared history**.

The local baseline snapshot is identical to GitHub `main` at commit `e2d448e`, but the commits are unrelated.

**Do not force-push. Do not push `release/prepare-first-release` as-is.**

## What is ready locally

- Folder: `C:\Users\DELL\Downloads\Breezy-trace-new-ui (6)\Breezy-trace`
- Branch: `release/prepare-first-release`
- Local commits:
  - `099a266` — baseline import
  - `bd79ce3` — release metadata and seven trivial lint fixes
  - `af527fc` — decision log
  - `1b84fb8` — test isolation and local project-list cleanup
- Package: `breezy-trace` version `0.1.0`
- PyPI name: free as of 11/11/26
- Tests: **163 passed, 2 skipped**
- Build: wheel and source package built; `twine check` passed
- Clean install: all three help commands work
- License: MIT, copyright “Copyright (c) 2026 Breezy”
- User-facing dependencies: MIT; development-only notes recorded in the decision log
- Real local projects kept: `DELL`, `cyrrus`, `Breezy-trace`
- Test-created project entries removed; database backup kept in the temporary folder

## Safe next step

Recreate the release work on top of GitHub `main`:

1. Fetch the existing history (already done locally, safe and read-only):
   ```text
   git fetch origin main
   ```
2. Create a new branch from GitHub `main`:
   ```text
   git switch -c release/prepare-first-release-clean origin/main
   ```
3. Apply the three local release commits in order:
   ```text
   git cherry-pick bd79ce3 af527fc 1b84fb8
   ```
   The local baseline is identical to GitHub `main`, so these changes should apply cleanly.
4. Run the checks again:
   ```text
   ruff check .
   pytest -n auto
   python -m build
   python -m twine check dist/*
   ```
   Run tests with temporary files outside the user’s home folder if needed.
5. Push the new branch and open a pull request into `main`:
   ```text
   git push -u origin release/prepare-first-release-clean
   ```
6. Wait for GitHub CI to pass, then merge the pull request.
7. Publish only after the owner gives a final explicit yes. The existing GitHub workflow publishes to PyPI from a published GitHub release.

## Do not

- Do not force-push.
- Do not push the current unrelated branch as-is.
- Do not create a tag or GitHub release without approval.
- Do not upload to PyPI without a final explicit yes.
- Do not commit `dist/`, `build/`, `.venv/`, or cache files.
- Do not remove the real local projects from the Breezy Trace database.

## Release details prepared

- Tag: `v0.1.0`
- Release title: `Breezy Trace 0.1.0`
- Release notes: the `[0.1.0] - 2026-11-12` section of `CHANGELOG.md`
- Publish trigger: publishing the GitHub release runs `.github/workflows/publish.yml`
- Requirement: the release commit must be part of `main`
- Do not create the release until the owner gives a final explicit yes

## Owner decisions still needed

- Final approval to publish version `0.1.0` after CI passes.
- Confirmation that the rebuilt branch and pull request are correct.

## Update — 12/11/26: rebuilt on existing GitHub history

The release work has been rebuilt in a new folder on a branch based on the existing GitHub `main`.

- New folder: `C:\Users\DELL\Downloads\Breezy-trace-release-clean`
- New branch: `release/prepare-first-release-clean`
- GitHub base: `origin/main` at `e2d448e`
- Applied release commits:
  - `b81e663` — release metadata and lint fixes
  - `d5747e3` — decision log
  - `086434c` — test isolation and local project-list cleanup
  - `9528c6d` — handoff and GitHub history warning
- Tests: **163 passed, 2 skipped**
- Build: wheel and source package built; `twine check` passed
- Clean install: `breezy-trace --help`, `btrace --help`, and `python -m breezy_trace --help` all work
- Isolation check: a separate data folder showed no projects, so the real list was untouched
- Real projects still present: `DELL`, `cyrrus`, `Breezy-trace`
- Nothing was pushed, tagged, or published.

**Use the new folder and new branch for the push and pull request. The original folder and branch are the backup.**

The rebuild steps described above are already complete on the new branch. Only the remaining steps apply now: push the new branch, open a pull request into `main`, wait for CI, and merge. The original instructions above still describe the safe approach; the branch and folder names in this update replace the old ones.

## Update — 12/11/26: professional release polish

The branch received a final quality pass before the push.

- `9270156` — applied `ruff format` across the codebase and replaced small `try`/`except`/`pass` blocks with `contextlib.suppress`
- `49a6659` — added release metadata, PyPI install instructions, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `MANIFEST.in`, a version-consistency test, and stricter CI checks

Key improvements:

- README now leads with `pip install breezy-trace`, has a structured quick start, keyboard reference, CLI reference, privacy notes, and a clear scope/limitations section.
- Package metadata now includes maintainer, license files, changelog/documentation links, supported dependency ranges, and a modern scanner compatibility check.
- The source package includes the release documents, tests, and benchmark script.
- CI now checks `pip check`, `ruff format --check`, and `ruff check` before tests.
- The release checklist now requires formatting and changelog checks.

Verification after the polish:

- `ruff format --check .` passed.
- `ruff check .` passed.
- Tests: **164 passed, 2 skipped**.
- Wheel and source package rebuilt.
- `twine check` passed both files.
- Clean install passed `pip check` and all three help commands.
- Isolated data-folder check showed no projects, so the real list was untouched.
- Nothing was pushed, tagged, or published.

The branch is ready for the authorized person to push and open the pull request. The release tag and notes are prepared but must not be created until the owner gives a final explicit yes after CI passes.
