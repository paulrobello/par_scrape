# Testing Guide

This document describes how to run the test suite for `par_scrape`, what files were modified, and the current test coverage.

## 1. Environment Setup

The project uses `uv` for dependency management and `pytest` for testing.

From the project root (where `pyproject.toml` is located), install the development (including test) dependencies with:

bash
uv sync --group dev
You do not need to activate a virtual environment manually when using uv run. uv will create and manage .venv for you.

2. Running Tests
Run the full test suite with:

bash
Copy code
uv run pytest
To see verbose output:

bash
Copy code
uv run pytest -v
To run only a specific test file:

bash
Copy code
uv run pytest tests/test_utils.py -v
uv run pytest tests/test_scrape_data.py -v
uv run pytest tests/test_crawl.py -v
3. Pytest Configuration
Pytest is configured in pyproject.toml. Important settings:

testpaths = ["tests"] ensures all tests live under the tests directory.

python_files = ["test_*.py"] ensures test files follow the test_*.py naming pattern.

addopts = "-v --cov=par_scrape --cov-report=term-missing" enables verbose mode and coverage reporting by default.

pythonpath = ["src"] allows direct imports from par_scrape without needing relative paths.

4. Files Modified and Created
Source Files
src/par_scrape/exceptions.py
Added:

ParScrapeError (base exception)

CrawlConfigError for invalid crawl or scrape configuration

ProviderConfigError for invalid AI provider or model configuration

Additional crawl related exceptions moved here from crawl.py:

InvalidURLError

ScrapeError

RobotError

src/par_scrape/utils.py
Added several helper functions:

normalize_url

extract_domain

chunk_list

safe_divide

merge_dicts

These functions normalize URLs, extract domains, split lists into chunks, safely divide numbers, and merge dictionaries. They are now covered by unit tests with both valid and edge case inputs.

src/par_scrape/scrape_data.py
No major logic changes, but this file is now covered by tests. Tests cover:

save_raw_data

create_dynamic_model

create_container_model

format_data

save_formatted_data

The tests use mocks for the LLM integration and verify that output files (JSON, CSV, Markdown) are created correctly.

src/par_scrape/crawl.py
Additional exception handling and small logic fixes were added here, including:

Using the custom exceptions from exceptions.py.

Fixing the extract_links robots logic so that URLs are only skipped when disallowed by robots.txt.

Removing duplicated code in add_to_queue.

Replacing a raise and immediately catch pattern with simpler conditional checks and console.print.

Test Files
tests/test_utils.py
Uses pytest.mark.parametrize to test multiple input and output cases for:

normalize_url

extract_domain

chunk_list

safe_divide

merge_dicts

Includes edge and error condition tests, such as:

Invalid URLs

Invalid chunk sizes

Division by zero

tests/test_scrape_data.py
Covers the data formatting and persistence utilities:

Tests file creation and dynamic Pydantic model generation.

Mocks LLM calls using pytest-mock.

Covers both success and error paths for:

save_raw_data

format_data

save_formatted_data

Validates that JSON, CSV, and Markdown outputs are created correctly.

Tests error handling when model_dump returns an unsupported type (raises ValueError).

tests/test_crawl.py
Uses pytest.mark.parametrize and fixtures to exercise core crawling helpers and queue logic:

Functions covered include:

is_valid_url

clean_url_of_ticket_id

check_robots_txt (with mocked responses)

get_next_urls

extract_links

should_exclude_url

get_url_output_folder

set_crawl_delay

get_queue_size

get_queue_stats

add_to_queue

mark_complete

mark_error

init_db (database initialization)

Edge cases tested include:

Invalid URLs

URLs with ticket ids

Empty queues

Missing URLs in mark_complete and mark_error

Non HTML content and excluded asset types

Configuration File
pyproject.toml
Uses [dependency-groups.dev] for development and test dependencies (installed via uv sync --group dev).

[tool.pytest.ini_options] is configured to control test discovery, verbosity, and coverage reporting.

5. Custom Exceptions
Defined in src/par_scrape/exceptions.py:

ParScrapeError
Base exception for all project specific errors.

CrawlConfigError
Raised when crawl or scrape configuration is invalid.
Examples: missing URL, unsupported crawl type, non positive page limits.

ProviderConfigError
Raised when AI provider or model configuration is invalid.
Examples: unsupported provider string, missing model for a given provider.

InvalidURLError, ScrapeError, RobotError
Crawl related errors used for invalid URLs, scraping failures, and robots.txt issues.

CrawlConfigError is currently used in utils.normalize_url, while ProviderConfigError is reserved for provider and model configuration validation. Crawl specific exceptions are used in crawl.py to keep error handling consistent.

6. Test Coverage Summary
Results from the latest test run using:

bash
Copy code
uv run pytest -v
which automatically includes coverage reporting via addopts:

File	Coverage	Notes
src/par_scrape/utils.py	~96%	Helper functions tested with valid and invalid cases
src/par_scrape/scrape_data.py	~73%	Core functions tested, including file I/O and LLM mocks
src/par_scrape/exceptions.py	100%	All custom exceptions covered
src/par_scrape/enums.py	100%	Enum members and values tested
src/par_scrape/crawl.py	~77%	Core crawling helpers, queue logic, and robots handling
Overall project coverage	~52%	Focused on core logic; CLI and full crawl orchestration are not yet covered

To view a detailed coverage report in the terminal:

bash
Copy code
uv run pytest --cov=par_scrape --cov-report=term-missing
7. Known Issues and Limitations
Tests for format_data use mocks rather than calling actual AI APIs.

Coverage focuses on utilities, data formatting, and crawl helpers, not on:

Command line execution in __main__.py

Full end to end crawling flows

Future improvements could include:

Tests for the command line interface in src/par_scrape/__main__.py

Higher level tests for full crawl runs in src/par_scrape/crawl.py

sql
Copy code

You can:

1. Open `TESTING.md` in your editor.  
2. Select all, paste this over the top, and save.  
3. Then:

```bash
git add TESTING.md
git commit -m "docs: update TESTING.md for uv dev group and 52 percent coverage"
git push