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

### `src/par_scrape/utils.py`

Helper functions:

- `chunk_list` — splits a list into evenly sized chunks
- `safe_divide` — divides two numbers, returning 0.0 on division by zero
- `merge_dicts` — merges two dicts, with the second overwriting keys from the first

### `src/par_scrape/scrape_data.py`

Data formatting and persistence:

- `save_raw_data` — saves markdown content to a file
- `create_dynamic_model` — builds a Pydantic model from a list of field names
- `create_container_model` — wraps a model in a list container
- `format_data` — invokes an LLM to extract structured data
- `save_formatted_data` — saves extracted data as JSON, CSV, Excel, and/or Markdown

### `src/par_scrape/crawl.py`

Crawl queue and helpers:

- `is_valid_url`, `clean_url_of_ticket_id`, `should_exclude_url`
- `check_robots_txt` — checks `robots.txt` with a 10-second fetch timeout
- `extract_links` — extracts and filters links from HTML
- `get_url_output_folder` — maps a URL to a local output path
- `init_db`, `add_to_queue`, `get_next_urls`, `get_queue_size`, `get_queue_stats`
- `mark_complete`, `mark_error`, `set_crawl_delay`

## 5. Test Files

### `tests/test_crawl.py`

Covers core crawling helpers and queue logic using `pytest.mark.parametrize` and fixtures.
Uses `monkeypatch` and `mock.patch.object` to isolate the SQLite database path.

Edge cases include: invalid URLs, URLs with ticket IDs, empty queues, missing URLs in `mark_complete`/`mark_error`, excluded asset types.

### `tests/test_utils.py` *(if present)*

Covers `chunk_list`, `safe_divide`, and `merge_dicts` with valid, edge-case, and error inputs.

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
| `src/par_scrape/utils.py` | 100% | All helpers with valid and edge-case inputs |
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
