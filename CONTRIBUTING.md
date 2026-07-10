# Contributing to PAR Scrape

Contributions are welcome. This guide covers setting up a development environment, running the verification gate before opening a pull request, and the code style the project expects.

## Table of Contents

- [Development Setup](#development-setup)
- [Verification Gate](#verification-gate)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Expectations](#pull-request-expectations)

## Development Setup

PAR Scrape targets Python 3.11 or higher and uses [`uv`](https://pypi.org/project/uv/) for dependency management. Install `uv` first (see the [Prerequisites](README.md#prerequisites) section of the README), then sync dependencies and create the virtual environment:

```bash
make setup
```

`make setup` runs `uv lock` followed by `uv sync`, which creates `.venv` automatically. You do not need to activate the virtual environment manually; prefix commands with `uv run` (for example `uv run par_scrape --help`).

To recreate the virtual environment from scratch:

```bash
make resetup
```

## Verification Gate

All pull requests must pass `make checkall` before review. It runs four steps in order:

```bash
make checkall
```

The steps, each also available individually:

| Step | Command | What it does |
| --- | --- | --- |
| Format | `make format` (alias `make fmt`) | Reformats `src/par_scrape` and `tests` with `ruff format` |
| Lint | `make lint` | Non-mutating `ruff check` over `src/par_scrape` and `tests` |
| Typecheck | `make typecheck` | Static type checks with `pyright` |
| Test | `make test` | Runs the `pytest` suite with coverage |

If `make checkall` reports any error, fix it before pushing. Auto-fixable lint findings can be resolved with `make lint-fix`, but re-run the full gate afterward.

## Pre-commit Hooks

The repository ships a `.pre-commit-config.yaml` (including a `gitleaks` hook for secret detection). Install the hooks once after cloning:

```bash
pre-commit install
```

To run every hook across all files (for example before pushing, or if you skipped the install):

```bash
make pre-commit
```

Keep hooks up to date with `make pre-commit-update`.

## Code Style

The conventions below are enforced by `ruff` and `pyright` and summarized from `CLAUDE.md`:

- **Python**: 3.11+. Use modern builtin generics (`list`, `dict`, `tuple`) instead of `typing.List`, `typing.Dict`, `typing.Tuple`.
- **Line length**: 120 characters.
- **Indentation**: 4 spaces. No trailing whitespace.
- **Quotes**: Double quotes.
- **Imports**: Grouped and sorted by `ruff`.
- **Type annotations**: Required on all public functions and new code.
- **Docstrings**: Google style for every public function and module.
- **File I/O**: Use `pathlib.Path` for all filesystem operations and pass `encoding="utf-8"` to text file operations.
- **Console output**: Use the `rich` library (`console_out`) for user-facing output.
- **Error handling**: Catch specific exceptions (never bare `except:`). Network requests must have a 10-second timeout.

When editing existing code, match the surrounding style rather than reformatting unrelated lines.

## Testing

Test conventions, the shared fixtures, and a per-file inventory of the suite are documented in [TESTING.md](TESTING.md). New behavior should come with tests; run `make test` (or `make checkall`) to confirm they pass.

## Pull Request Expectations

- **Small and atomic**: one focused change per PR. Mix refactor, feature, and fix into separate PRs where possible.
- **Conventional commit messages**: use prefixes such as `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:` (for example `fix: respect --output-folder when crawling`).
- **Branch naming**: use a short descriptive name prefixed with `fix/`, `feat/`, `docs/`, etc. (for example `fix/audit-remediation`).
- **Green gate**: `make checkall` passes on your branch before you request review.
- **Tests**: include tests for new behavior and update tests when a contract changes. Update documentation (`README.md`, `TESTING.md`, `CHANGELOG.md`) when the user-facing behavior changes.

## Questions

For bugs and feature requests, open a [GitHub issue](https://github.com/paulrobello/par_scrape/issues). For everything else, open a draft PR to start the discussion.
