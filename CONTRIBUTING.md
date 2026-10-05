# Contributing

Issues and pull requests from forks are welcome. This is a personal project maintained in
spare time, so reviews can take a while.

## Before opening a pull request

- Open an issue first for anything bigger than a bug fix, so we agree on the shape before
  you spend time on it.
- Keep each PR to one change.
- Add or update a test in `tests/`. The suite drives the app headless with Textual's `Pilot`
  against a fake Jira and needs no network.
- Add one line under an `## Unreleased` heading at the top of `CHANGELOG.md`.
- No real hostnames, project keys, or account ids in code, tests, or examples. Use
  `example.atlassian.net` and `PROJ-123`.

## Running the checks

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format .
uv run pytest -q
```

CI runs the same three commands on Python 3.11, 3.12 and 3.13. Workflows on PRs from
forks start only after a maintainer approves them.

## Branches and merging

Name branches after the change, for example `comment-editor-undo`. PRs are squash merged,
so the PR title becomes the commit message; write it as a sentence in the imperative.

Releases are made from `main` by the maintainer: version bump, changelog section, tag.
