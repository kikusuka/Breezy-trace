## Summary

Describe the user-visible change and why it is needed.

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Packaging or CI
- [ ] Refactor

## Checks

- [ ] `ruff format --check .`
- [ ] `ruff check .`
- [ ] `pytest`
- [ ] `python -m build`
- [ ] `python -m twine check dist/*`

## Safety

- [ ] Git access remains read-only.
- [ ] No telemetry or background network calls were added.
- [ ] No prompts, transcripts, source text, comments, or docstrings are stored.
- [ ] Tests use `BREEZY_TRACE_DATA_DIR` or a temporary database and do not touch real user data.

## Notes

Add anything reviewers should know, including follow-up work or known limitations.
