# PAR Scrape Developer Guidelines

## Build/Lint/Test Commands
- Setup: `make setup`
- Run app: `make run ARG1="--help"`
- Run format, lint, typecheck: `make checkall`

## Code Style
- Python version: 3.10+
- Line length: 120 characters
- Indentation: 4 spaces
- Type annotations required (use `list`, `dict`, `tuple` over `List`, `Dict`, `Tuple`)
- Docstrings: Google style
- Imports: grouped, sorted with `ruff`
- Quotes: double quotes
- Use pathlib for file operations
- Set utf-8 encoding for all text file operations
- Rich library for console output
- The linter does not like trailing whitespace

## Error Handling
- Proper exception handling with specific exceptions
- Ensure web requests have a 10-second timeout
- Retry mechanism for network operations

## Package Management
- Use `uv` instead of pip/poetry (`uv add`, `uv remove`)

## Project Structure
- Source code in `src/par_scrape/`
- Main CLI app entry point: `__main__.py`
- Static typing enforced with pyright
