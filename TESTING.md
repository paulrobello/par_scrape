# Testing Guide

This document describes how to run the test suite for `par_scrape`, what is covered, and the current test coverage.

## 1. Environment Setup

The project uses `uv` for dependency management and `pytest` for testing.

From the project root (where `pyproject.toml` is located), install development dependencies with:

```bash
uv sync --group dev
```

You do not need to activate a virtual environment manually when using `uv run`. It creates and manages `.venv` automatically.

## 2. Running Tests

Run the full test suite:

```bash
uv run pytest
```

Verbose output:

```bash
uv run pytest -v
```

Run a specific test file:

```bash
uv run pytest tests/test_crawl.py -v
```

## 3. Pytest Configuration

Pytest is configured in `pyproject.toml` under `[tool.pytest.ini_options]`:

- `testpaths = ["tests"]` — all tests live under `tests/`
- `python_files = ["test_*.py"]` — test files follow the `test_*.py` naming pattern
- `addopts = "-v --cov=par_scrape --cov-report=term-missing"` — verbose output and coverage reporting enabled by default
- `pythonpath = ["src"]` — allows direct imports from `par_scrape` without relative paths

## 4. Source Files Under Test

### `src/par_scrape/exceptions.py`

Custom exception hierarchy:

- `ParScrapeError` — base exception for all project-specific errors
- `CrawlConfigError` — invalid crawl or scrape configuration
- `ProviderConfigError` — invalid AI provider or model configuration
- `InvalidURLError`, `ScrapeError`, `RobotError` — crawl-specific errors

### `src/par_scrape/scrape_data.py`

Data formatting and persistence:

- `save_raw_data` — saves markdown content to a file
- `create_dynamic_model` — builds a Pydantic model from a list of field names
- `create_container_model` — wraps a model in a list container
- `format_data` — invokes an LLM to extract structured data
- `save_formatted_data` — saves extracted data as JSON, CSV, Excel, and/or Markdown

### `src/par_scrape/crawl.py`

Crawl queue and helpers:

- `is_valid_url`, `should_exclude_url`
- `check_robots_txt` — checks `robots.txt` with a 10-second fetch timeout
- `extract_links` — extracts and filters links from HTML
- `get_url_output_folder` — maps a URL to a local output path
- `init_db`, `add_to_queue`, `get_next_urls`, `get_queue_stats`
- `mark_complete`, `mark_error`, `set_crawl_delay`

## 5. Test Files

The suite lives entirely under `tests/`. The files, in order of layer from lowest to highest:

### `tests/conftest.py`

Shared pytest fixtures. Defines the canonical `db_path` fixture (established in ARC-011): it yields a `tmp_path`-backed SQLite database, initializes the schema on it via explicit `db_path=` injection, and also points `queue_db.DB_PATH` at the same file for code that still reads the module global. Every queue test depends on this fixture for isolation.

### `tests/test_enums.py`

Covers the `enums.py` value types: `CleanupType`, `OutputFormat` members and values, enum uniqueness, and iterability. Pure data tests with no I/O.

### `tests/test_exceptions.py`

Covers the typed exception hierarchy in `exceptions.py`: the `classify_error` router (isinstance routing, substring fallback, and isinstance-takes-precedence rule) and that `ScrapeError` is a subclass of the `ParScrapeError` base.

### `tests/test_crawl.py`

The largest test file; covers the persistence and URL-filtering layers reached through the `crawl.py` compatibility shim. Class-grouped, heavily parametrized:

- `TestCrawlFunctions` — `is_valid_url`, `check_robots_txt` (including fail-open on fetch error), `get_next_urls` rate-limit selection, `extract_links`, `should_exclude_url` (with segment-anchoring edge cases), `get_url_output_folder` (including traversal-netloc rejection), `set_crawl_delay`.
- `TestQueueFunctions` — `get_queue_stats`, `add_to_queue` (including the run-name-in-URL edge case).
- `TestMarkFunctions` — `mark_complete` / `mark_error`, including the missing-URL no-op cases.
- `TestFilePathsJsonColumn` — the v2 schema `file_paths` JSON column written by `mark_complete`.
- `TestQueueHelpers` — `get_url_depth` and `increase_crawl_delay` (double-and-cap).
- Module-level `test_init_db*` — schema initialization and the incompatible-database rename-aside upgrade path.

### `tests/test_scrape_data.py`

Covers `scrape_data.py`: `save_raw_data` (directory vs. non-directory base), `create_dynamic_model` / `create_container_model`, `format_data` success and failure (LLM mocked; asserts `ScrapeError` on failure per ARC-001), and `save_formatted_data` across formats including the CSV formula-injection neutralizer, the empty-DataFrame `ScrapeError`, and per-format write failures (ARC-001 raise-on-failure contract).

### `tests/test_runner.py`

Covers the `runner.py` orchestration layer extracted in ARC-002: `process_url` for the markdown-only path (marks `COMPLETED` and writes the file) and the HTML-to-markdown timeout path (classifies the error and marks `ERROR`), plus a CLI markdown-only smoke test through `main()`. Uses `mocker` plus the shared `db_path` fixture.

## 6. Custom Exceptions

Defined in `src/par_scrape/exceptions.py`:

| Exception | Description |
|---|---|
| `ParScrapeError` | Base exception for all project-specific errors |
| `CrawlConfigError` | Invalid crawl or scrape configuration |
| `ProviderConfigError` | Invalid AI provider or model configuration |
| `InvalidURLError` | URL failed validation |
| `ScrapeError` | General scraping failure |
| `RobotError` | `robots.txt` disallowed or fetch failure |

## 7. Test Coverage Summary

| File | Coverage | Notes |
|---|---|---|
| `src/par_scrape/exceptions.py` | 100% | All custom exceptions covered |
| `src/par_scrape/enums.py` | 100% | Enum members and values covered |
| `src/par_scrape/crawl.py` | ~77% | Core helpers and queue logic; full crawl orchestration not covered |
| `src/par_scrape/scrape_data.py` | ~73% | LLM calls mocked; file I/O and model creation covered |
| `src/par_scrape/__main__.py` | 0% | CLI orchestration not yet tested |
| **Overall** | **~51%** | Focused on core logic |

To view a detailed coverage report:

```bash
uv run pytest --cov=par_scrape --cov-report=term-missing
```

## 8. Known Limitations

- `format_data` tests use mocks rather than live AI APIs.
- `__main__.py` has no test coverage (CLI orchestration and full crawl flows).
