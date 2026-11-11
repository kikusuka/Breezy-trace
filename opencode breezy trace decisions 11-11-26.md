# OpenCode Breezy Trace Decisions — 11/11/26

Project: **Breezy Trace**  
PyPI name: **breezy-trace**  
Local folder: `C:\Users\DELL\Downloads\Breezy-trace-new-ui (6)\Breezy-trace`  
Release branch: `release/prepare-first-release`

## Decisions taken

1. **Release this exact folder.** The owner confirmed this is the correct Breezy Trace project folder.
2. **Use a separate local git history for just this folder.** The folder was sitting inside an accidental repository covering the whole Windows user folder, with an unrelated GitHub remote. The owner approved creating a fresh local history for Breezy Trace only. Other personal files were left untouched.
3. **Do not use the unrelated remote.** The old user-folder repository pointed to `https://github.com/kikusuka/ivy-code-base-.git`, which is not Breezy Trace.
4. **Keep version `0.1.0`.** PyPI returned “not found” for `breezy-trace`, so the name is free and the version was not already published.
5. **Use Python 3.13.15 for the clean test environment.** The package supports Python 3.11 and newer.
6. **Fix only trivial style problems.** Seven automatic lint fixes were made: import ordering and unused suppression comments. No behavior was changed.
7. **Test result:** the first full run had two failures caused by test folders being inside the accidental home-folder repository. Rerunning the complete suite with temporary files outside the home folder gave **162 passed, 2 skipped**.
8. **Add release metadata:** keywords, Development Status Alpha, Console environment, Developers audience, Git topic, author **Breezy Labs**, and Homepage/Issues links to `https://github.com/kikusuka/Breezy-trace`.
9. **License:** `LICENSE` is MIT, with the line **Copyright (c) 2026 Breezy**. The owner approved keeping it unchanged.
10. **Dependency licenses:** user-facing dependencies are MIT, including the optional code extra. Development tools are MIT except twine, which is Apache-2.0. Two development-only transitive packages were noted: certifi (MPL-2.0) and docutils (lists a GPL option). They do not ship to users. The owner accepted these notes on 11/11/26.
11. **Build verification:** `python -m build` produced a wheel and source package; `twine check` passed. The wheel was installed into a brand-new environment and these commands all worked:
    - `breezy-trace --help`
    - `btrace --help`
    - `python -m breezy_trace --help`
12. **Wheel contents:** 31 Python package files, the MIT license, and package metadata. No tests, caches, or build leftovers are in the wheel.
13. **Owner approval:** the prepared metadata was approved on 11/11/26.
14. **GitHub connection:** the owner approved connecting the local repository to `https://github.com/kikusuka/Breezy-trace`. The address was added locally as `origin`. **No push, tag, GitHub release, or PyPI upload was performed.**
15. **Terminal test:** the owner asked to test the project once. A new terminal window was opened with the installed package on 11/11/26, and the process started successfully. A non-interactive check also ran `breezy-trace --version` and `breezy-trace projects`.
16. **Publishing:** the owner answered “mostly yes” about publishing. That is not recorded as final approval, and nothing was published. The recommendation is to merge the release branch into main, push it, let CI run, and publish only after a final explicit yes.
17. **This decision log** was created on 11/11/26. The file name uses hyphens because `/` is not valid in Windows file names.
18. **Local test data:** the automated tests left sample project entries in the real local Breezy Trace database, visible in `breezy-trace projects`. No cleanup was done at first, because some entries may be real projects.
19. **Mock data cleanup approved:** the owner approved removing only test-created entries. Ten entries whose paths were inside pytest temporary folders were removed. The real entries `DELL`, `cyrrus`, and `Breezy-trace` were kept. A backup of the database was made first at `C:\Users\DELL\AppData\Local\Temp\opencode\trace-before-cleanup-20261111-222258.sqlite3`.
20. **Test isolation fixed:** added support for `BREEZY_TRACE_DATA_DIR` in `config.py`, updated the three subprocess tests to use it, and added a regression test. The full suite then passed with **163 passed, 2 skipped**, and the real project list stayed unchanged.
21. **Rebuild after the fix:** the wheel and source package were rebuilt; `twine check` passed; a brand-new environment installed the wheel; all three help commands worked; `breezy-trace projects` with the override showed no projects, confirming isolation.
22. **Publishing:** still on hold. The owner will decide after the release branch is merged, pushed, and CI passes. Nothing was pushed or published.
23. **GitHub history discovered:** the GitHub repository already has its own `main` and many branches. GitHub `main` is at `e2d448e`. The local baseline snapshot is identical to that tree, but the local commits have no shared history with it. Pushing the current branch as-is would be wrong.
24. **Safe release path:** rebuild the release work on a new branch from `origin/main`, apply the four release commits, rerun tests and build, then push that branch and open a pull request. Do not force-push and do not push the current unrelated branch as-is.
25. **Handoff:** the owner approved a plain-English handoff note for the person who will push and run GitHub checks. It is saved as `opencode breezy trace release handoff 11-11-26.md`.
26. **Rebuild approved in a new folder:** the owner approved rebuilding the release work on top of the existing GitHub `main` in a new project folder, keeping the original folder and branch as a backup.
27. **Clean rebuild:** created the new folder `C:\Users\DELL\Downloads\Breezy-trace-release-clean` and branch `release/prepare-first-release-clean` from `origin/main` at `e2d448e`. The four local release commits were applied as `b81e663`, `d5747e3`, `086434c`, and `9528c6d`.
28. **Rebuilt branch checks:** `ruff` passed; tests passed with **163 passed, 2 skipped**; the wheel and source package built; `twine check` passed; a clean install ran all three help commands successfully; the isolated data-folder check showed no projects.
29. **Real local list:** remained unchanged with `DELL`, `cyrrus`, and `Breezy-trace` after the rebuilt test run.
30. **Handoff updated:** a new “Update — 12/11/26” section in the handoff note gives the new folder, new branch, commit list, test/build results, and the instruction to use the new branch for the pull request.
31. **Publishing:** still on hold. Nothing was pushed, tagged, released, or uploaded. The owner will decide on publishing after the pull request and CI checks pass.
32. **Professional release polish approved:** the owner asked to clean the code enough for a professional PyPI release and to prepare the release details.
33. **README rewritten:** install instructions now lead with `pip install breezy-trace`, followed by a structured quick start, keyboard reference, CLI reference, data/privacy notes, development commands, and scope/limitations. The old run-on paragraph and duplicate sentence were removed.
34. **Release documents added:** `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `MANIFEST.in`. The source package now includes the release documents, tests, and benchmark script.
35. **Metadata hardened:** setuptools requirement raised to 77 for PEP 639 license files; added maintainer, license files, documentation and changelog links; added supported upper bounds for `platformdirs`, `textual`, and `rich`.
36. **Codebase formatted:** `ruff format` applied to the project. Small `try`/`except`/`pass` blocks in `app.py`, `code_index.py`, and `settings.py` were replaced with `contextlib.suppress`. The lint configuration now enables import sorting, bugbear, blind-exception, pyupgrade, simplify, comprehension, and unused-`noqa` checks.
37. **CI hardened:** CI and the publish workflow now run `pip check` and `ruff format --check` before lint and tests. The release checklist requires formatting and changelog checks.
38. **Verification after polish:** `ruff format --check .` passed; `ruff check .` passed; tests passed with **164 passed, 2 skipped**; wheel and source package rebuilt; `twine check` passed both; clean install passed `pip check` and all three help commands; isolated data-folder check showed no projects.
39. **Release details prepared:** tag `v0.1.0`, title `Breezy Trace 0.1.0`, and release notes from the `[0.1.0] - 2026-11-12` section of `CHANGELOG.md`. The release must not be created until the owner gives a final explicit yes after CI passes.
40. **Push remains blocked for the assistant:** nothing was pushed, tagged, released, or uploaded. An authorized person must push `release/prepare-first-release-clean` and open the pull request.

## Saved history

- `099a266` — baseline import of Breezy Trace 0.1.0 on `main`
- `bd79ce3` — release preparation on `release/prepare-first-release`

## Next steps

1. Review the new folder and branch `release/prepare-first-release-clean`.
2. An authorized person pushes the branch and opens a pull request into `main`.
3. Wait for CI and the dependency security check to pass.
4. Merge the pull request after review.
5. The owner gives a final explicit yes or no on publishing.
6. If yes, create GitHub release `v0.1.0` from `main` using the `CHANGELOG.md` notes.
7. Confirm the publish workflow succeeds and the package is installable from PyPI.
