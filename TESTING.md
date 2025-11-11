Testing Guide

This document describes how to run the test suite for par_scrape, what files were modified, and the current test coverage.

1. Environment Setup

The project uses uv for dependency management and pytest for testing.

From the project root (where pyproject.toml is located):

uv sync --extra test


This installs the main dependencies and the testing extras:

pytest

pytest-mock

pytest-cov

You do not need to activate a virtual environment manually when using uv run.

2. Running Tests

Run the full test suite with:

uv run pytest


To see verbose output:

uv run pytest -v


To run only a specific test file:

uv run pytest tests/test_utils.py -v
uv run pytest tests/test_scrape_data.py -v

3. Pytest Configuration

Pytest is configured in pyproject.toml:

testpaths = ["tests"] ensures all tests live under the tests directory

python_files = ["test_*.py"] ensures test files follow the test_*.py naming pattern

addopts = "-v --cov=par_scrape --cov-report=term-missing" enables verbose mode and coverage reporting

pythonpath = ["src"] allows direct imports from par_scrape

4. Files Modified and Created
Source Files

src/par_scrape/exceptions.py
Added:

ParScrapeError (base exception)

CrawlConfigError for invalid crawl or scrape configuration

ProviderConfigError for invalid AI provider or model configuration

src/par_scrape/utils.py
Added several helper functions:

normalize_url

extract_domain

chunk_list

safe_divide

merge_dicts

These functions normalize URLs, extract domains, split lists into chunks, safely divide numbers, and merge dictionaries.

src/par_scrape/scrape_data.py
No major logic changes, but this file is now fully tested.
Tests cover:

save_raw_data

create_dynamic_model

create_container_model

format_data

save_formatted_data

Test Files

tests/test_utils.py

Uses pytest.mark.parametrize to test multiple input/output cases for:

normalize_url

extract_domain

chunk_list

safe_divide

Includes edge and error condition tests (invalid URLs, invalid chunk sizes, division by zero)

Verifies CrawlConfigError is raised where appropriate

tests/test_scrape_data.py

Tests file creation and dynamic Pydantic model generation

Mocks LLM calls using pytest-mock

Covers both success and error paths for:

save_raw_data

format_data

save_formatted_data

Validates that JSON, CSV, and Markdown outputs are created correctly

Tests error handling when model_dump returns an unsupported type

Configuration File

pyproject.toml

Added project.optional-dependencies.test section for testing dependencies

Added [tool.pytest.ini_options] to configure test discovery and coverage

5. Custom Exceptions

Defined in src/par_scrape/exceptions.py:

ParScrapeError — Base exception for all project-specific errors

CrawlConfigError — Raised when crawl or scrape configuration is invalid

Examples: missing URL, unsupported crawl type, non-positive page limits

ProviderConfigError — Raised when AI provider or model configuration is invalid

Examples: unsupported provider string, missing model for a given provider

CrawlConfigError is currently used in utils.normalize_url, while ProviderConfigError is reserved for provider and model configuration validation.

6. Test Coverage Summary

Results from the latest test run using:

uv run pytest -v

File	Coverage	Notes
src/par_scrape/utils.py	~96%	All helper functions tested with valid and invalid cases
src/par_scrape/scrape_data.py	~73%	Core functions tested, including file I/O and LLM mocks
src/par_scrape/exceptions.py	100%	Fully covered
Overall project coverage	~21%	Focused on core logic; CLI and crawl modules excluded

To view a detailed coverage report:

uv run pytest --cov=par_scrape --cov-report=term-missing

7. Known Issues and Limitations

The tests for format_data use mocks rather than calling actual AI APIs.
Coverage focuses on utilities and data formatting, not on CLI execution or crawling logic.

Future improvements could include:

Tests for the command-line interface in __main__.py

Tests for dependency scanning in crawl.py