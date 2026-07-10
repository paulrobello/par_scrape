# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (Breaking)
- `--url` / `-u` is now a required option (previously defaulted to `https://openai.com/api/pricing/`). A bare `par_scrape` invocation no longer generates live traffic to a third-party site; pass `--url` explicitly. Existing scripts and README examples already pass `--url`/`-u` and are unaffected.
- Implicit `.env` loading from the current working directory has been removed (it could redirect API traffic and exfiltrate provider keys via an untrusted directory). Use the new opt-in `--env-file PATH` option to load a project-local env file; `~/.par_scrape.env` and the `~/.par-scrape.env` migration are unchanged.

### Security
- Replaced the third-party `Ilshidur/action-discord@master` action (mutable branch ref) with first-party `curl` notification steps in the privileged `publish-to-pypi`, `publish-to-testpypi`, and `github-release` jobs, removing a supply-chain compromise path for the published package.
- CSV/Excel exports now neutralize formula-injection cells (values starting with `= + - @` or tab/CR are prefixed with `'`).
- `--cleanup before/after` now deletes only the current run's output subtree and refuses unsafe targets, instead of recursively deleting the entire output root.
- URLs/exceptions printed from crawled content are now Rich-markup-escaped to prevent forged status output.
- URL hostnames are validated before being used to build output paths.

### Fixed
- **Critical:** failed LLM extractions are no longer silently recorded as `COMPLETED`. `format_data` and `save_formatted_data` now raise `ScrapeError`, so failures route to `mark_error` and the retry/resume system engages instead of losing data with a success exit code.
- `par_scrape` now exits non-zero on fatal errors (previously exited 0 on a fully failed run).
- robots.txt: an unreachable `robots.txt` no longer blocks every subsequent URL on a domain (fail-open), and the global robots lock is no longer held across the 10-second network fetch.
- Crawl URLs are no longer mutated: `clean_url_of_ticket_id` (which rewrote `--run-name docs` URLs like `/docs/intro` to `/intro`) has been removed; output paths now use a hash discriminator.
- Schema upgrades no longer delete the crawl-state database — incompatible DBs are renamed aside to `jobs.sqlite.bak-v*`.
- Per-format save failures now surface as page errors instead of silently missing the output.
- Guarded a `ZeroDivisionError` in the run summary; anchored URL-exclusion patterns to path segments (`/feed` no longer excludes `/feedback`).

### Changed
- Decomposed the 594-line `main()` into a testable `runner.py` orchestrator (`ScrapeConfig` + `process_url` / `run_crawl`); `main()` now parses options and delegates.
- Split the 747-line `crawl.py` into cohesive modules — `queue_db.py` (SQLite repository), `links.py`, `robots.py`, `paths.py` — with `crawl.py` kept as a compatibility re-export shim.
- Adopted the typed exception hierarchy with a single `classify_error()` (replacing two drifted substring-matching blocks); queue functions now take an injectable `db_path`.
- Collapsed per-output-format path columns into a single JSON `file_paths` column (schema v2).
- CI (`build.yml`) now runs automatically on push to `main` and on pull requests.
- Consolidated to a single pyright config (`pythonVersion = "3.11"`); added ruff bugbear rules; Makefile `lint` is now check-only and covers tests; added a `build` target.
- Removed import-time side effects (the package no longer mutates `os.environ` or the home directory on import).
- Removed unused `fastapi` and `tldextract` dependencies.

### Added
- `--env-file` option for explicit env-file loading.
- `CONTRIBUTING.md`, `docs/architecture.md`, and a README table of contents.
- Tests for the orchestrator (`tests/test_runner.py`) and `classify_error` (`tests/test_exceptions.py`); total coverage rose from 51% to 80%.

### Removed
- Dead code: `utils.py`, the unused `get_queue_size`, an unreachable exception handler, and vestigial pylint pragmas.

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

## [0.5.1]

### Added
- Support for Deepseek, XAI, and LiteLLM providers

### Changed
- Updated ai-core and dependencies
- Better pricing data

## [0.5.0]

### Added
- Support for OpenRouter provider

### Changed
- Updated ai-core and dependencies

## [0.4.9]

### Added
- Support for LlamaCPP and XAI Grok (via new par-ai-core)
- Support for Python 3.10

### Changed
- Updated to use new par-ai-core
- Better cost tracking
- Updated pricing data
- Better error handling

## [0.4.8]

### Added
- Anthropic prompt cache option

## [0.4.7]

### Changed
- **BREAKING**: `--pricing` CLI option now takes a string value of `details`, `cost`, or `none`
- Updating pricing data
- Pricing token capture and compute now much more accurate

### Added
- Pool of user agents that gets randomly pulled from

## [0.4.6]

### Added
- Support for Amazon Bedrock

### Fixed
- Minor bug fixes

### Changed
- Updating pricing data
- Removed some unnecessary dependencies
- Code cleanup

## [0.4.5]

### Added
- New `--wait-type` option to specify the type of wait to use (pause, sleep, idle, text, or selector)

### Removed
- `--pause` option (no longer needed with the `--wait-type` option)

### Changed
- Playwright is now the default scraper as it is much faster

### Fixed
- Playwright scraping now honors the headless mode

## [0.4.4]

### Changed
- Better Playwright scraping

## [0.4.3]

### Added
- Option to override the base URL for the AI provider

## [0.4.2]

### Added
- The `url` parameter can now point to a local `rawData_*.md` file for easier testing of different models without having to re-fetch the data
- Ability to specify a file with the extraction prompt

### Changed
- Tweaked extraction prompt to work with Groq and Anthropic (Google still does not work)
- Removed need for `~/.par-scrape-config.json`

## [0.4.1]

### Fixed
- Minor bug fixes for pricing summary

### Changed
- Default model for Google changed to `gemini-1.5-pro-exp-0827` (free and usually works well)

## [0.4.0]

### Added
- Support for Anthropic, Google, Groq, and Ollama providers
- Flag for displaying pricing summary (defaults to False)
- Pricing data for Anthropic

### Changed
- Updated `cleanup` flag to handle both before and after cleanup

### Removed
- `--remove-output-folder` flag (replaced by the updated `cleanup` flag)

## [0.3.1]

### Added
- `pause` and `sleep-time` options to control the browser and scraping delays

### Changed
- Default headless mode to False so you can interact with the browser

## [0.3.0]

### Fixed
- Location of `config.json` file
