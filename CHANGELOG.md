# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.3] - 2026-06-22

### Fixed
- SQLite connections were never closed; `with sqlite3.connect(...) as conn` only manages the transaction, leaking connections until garbage collection and emitting `ResourceWarning: unclosed database`. Now wrapped in `contextlib.closing()` across `crawl.py`, `__main__.py`, and tests

### Changed
- Updated all dependencies to latest versions (beautifulsoup4, pandas, pydantic, typer, par-ai-core, fastapi, build, pyright, ruff, pytest, and transitive deps)

## [0.9.2] - 2026-04-25

### Changed
- Updated all dependencies to latest versions (beautifulsoup4, pandas, python-dotenv, rich, typer, tabulate, par-ai-core, fastapi, tldextract, build, pyright, ruff, pre-commit, pytest, pytest-cov)
- Added `gitleaks` pre-commit hook for secret detection

## [0.9.1] - 2026-02-25

### Fixed
- `--output-folder` CLI argument was silently ignored; output always went to `./output` regardless of the flag
- `--display-output` never displayed content due to using string `.value` as a dict key instead of the `OutputFormat` enum member
- `robots.txt` fetch had no timeout; a slow or unresponsive server would hang the entire crawl indefinitely (now enforces 10-second timeout)
- `assert` used as control flow for LLM config guard — replaced with explicit `RuntimeError` (assertions are stripped with `-O`)
- Missing `encoding="utf-8"` on raw data `write_text()` call (used system locale on Windows)
- `print()` calls in `init_db()` bypassed Rich formatting — replaced with `console_out.print()`
- Redundant `conn.close()` inside a `with sqlite3.connect()` context manager block

### Changed
- Replaced `strenum` third-party dependency with stdlib `enum.StrEnum` (requires Python ≥ 3.11, which was already the minimum)
- `CrawlType`, `PageStatus`, and `ErrorType` enums now use `StrEnum` directly instead of `(str, Enum)` pattern
- `os.makedirs()` replaced with `Path.mkdir()` in `scrape_data.py`
- `os.path.exists()` replaced with `Path.exists()` in `__main__.py`
- `utils.chunk_list` and `utils.merge_dicts` now use `TypeVar` generics for proper type safety
- `make checkall` now includes `pytest` (tests were not run as part of the standard check)
- Added `fmt` Makefile target as alias for `format` (standard convention)
- Added `test` Makefile target
- Aligned `ruff.toml` `target-version` to `py311` (was `py312`, inconsistent with `requires-python = ">=3.11"`)
- Aligned `pyrightconfig.json` `pythonVersion` and `typeCheckingMode` with `pyproject.toml`

### Documentation
- Rewrote `TESTING.md`: fixed malformed code blocks, removed stray "Copy code" artifacts and git instructions, removed references to non-existent `normalize_url`/`extract_domain` functions

## [0.9.0] - 2026-02-13

### Changed
- Bumped version to 0.9.0
- Updated all dependencies to latest versions

## [0.8.3] - 2025-12-01

### Changed
- Updated dependencies and ensured Python 3.14 compatibility
- Python 3.14 is now the default and recommended version
- Maintains backward compatibility with Python 3.11, 3.12, and 3.13
- Updated Pyright configuration to target Python 3.14
- Updated all CI/CD workflows to use Python 3.14

## [0.8.2] - 2025-10-01

### Fixed
- Critical race conditions in database operations:
  - `get_next_urls()`: now uses atomic transactions to prevent duplicate URL processing in concurrent scenarios
  - `add_to_queue()`: made INSERT and UPDATE operations atomic
  - `ROBOTS_PARSERS`: added thread-safe locking for concurrent access
- Logic error in `crawl_delay` initialization that affected all domains instead of just the target
- Improved error handling for file operations with proper UTF-8 encoding

### Changed
- Updated all dependencies (anthropic, chromadb, fastapi, selenium, and more)
- Enhanced concurrency safety for multi-threaded/multi-process crawling

## [0.8.1] - 2025-09-01

### Changed
- Updated dependencies (ruff 0.14.2, pyright 1.1.407)
- Ensured compatibility with Python 3.13 (now the default version)
- Maintains backward compatibility with Python 3.11 and 3.12

## [0.8.0] - 2025-08-01

### Changed
- Updated deps and CI/CD workflows

## [0.7.1] - 2025-07-01

### Changed
- Updated par-ai-core and other dependencies

## [0.7.0] - 2025-06-01

### Added
- `--respect-robots` flag to check robots.txt before scraping
- `--respect-rate-limits` flag to respect per-domain rate limits
- `--reasoning-effort` and `--reasoning-budget` options for o1/o3 and Claude Sonnet 3.7

### Changed
- Major overhaul and fixing of crawling features
- Updated dependencies

## [0.6.1] - 2025-05-15

### Changed
- Updated ai-core

## [0.6.0] - 2025-05-01

### Added
- Basic site crawling
- Retry failed fetches
- HTTP authentication
- Proxy settings

### Fixed
- Bug where images were being stripped from markdown output

### Changed
- **BREAKING**: New `-O` option to specify desired output formats (defaults to markdown only, no AI required)
- Now retries 3 times on failed scrapes
- Now uses par_ai_core for URL fetching and markdown conversion
- Updated system prompt for better results
