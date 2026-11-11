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

## Owner decisions still needed

- Final approval to publish version `0.1.0` after CI passes.
- Confirmation that the rebuilt branch and pull request are correct.
