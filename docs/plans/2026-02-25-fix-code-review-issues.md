# Fix Code Review Issues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all critical, important, and minor issues identified in the code review of par_scrape v0.9.0.

**Architecture:** Direct file edits across crawl.py, __main__.py, scrape_data.py, enums.py, pyproject.toml, ruff.toml, pyrightconfig.json, Makefile, and tests. No new abstractions needed.

**Tech Stack:** Python 3.11+, uv, ruff, pyright, pytest

---

### Task 1: Fix crawl.py — StrEnum enums (Critical #1)

**Files:**
- Modify: `src/par_scrape/crawl.py`

**Step 1: Replace `(str, Enum)` pattern with `StrEnum`**

In `crawl.py`, change:
```python
from enum import Enum
```
to:
```python
from enum import StrEnum
```

And change the three enum class definitions:
```python
class CrawlType(StrEnum):
    """Types of web crawling strategies."""
    SINGLE_PAGE = "single_page"
    SINGLE_LEVEL = "single_level"
    DOMAIN = "domain"

class PageStatus(StrEnum):
    """Status flags for pages in the crawl queue."""
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"

class ErrorType(StrEnum):
    """Types of errors that can occur during crawling."""
    NETWORK = "network"
    PARSING = "parsing"
    ROBOTS_DISALLOWED = "robots_disallowed"
    INVALID_URL = "invalid_url"
    TIMEOUT = "timeout"
    OTHER = "other"
```

**Step 2: Run ruff check to verify fix**

Run: `uv run ruff check src/par_scrape/crawl.py`
Expected: No UP042 errors

**Step 3: Run tests**

Run: `uv run pytest tests/ -v -x`
Expected: All 67 tests pass

---

### Task 2: Fix crawl.py — print() → console_out (Important #6)

**Files:**
- Modify: `src/par_scrape/crawl.py`

**Step 1: Add console_out import and replace print() calls**

`crawl.py` already imports from `rich.console import Console` but doesn't import `console_out`.
Add import after existing imports:
```python
from par_ai_core.par_logging import console_out
```

Then change lines 380 and 384:
```python
# Before:
print(f"Removed incompatible database at {DB_PATH}")
# After:
console_out.print(f"[yellow]Removed incompatible database at {DB_PATH}[/yellow]")
```

```python
# Before:
print(f"Removed corrupted database at {DB_PATH}")
# After:
console_out.print(f"[yellow]Removed corrupted database at {DB_PATH}[/yellow]")
```

**Step 2: Remove redundant conn.close() (Important #9)**

In `init_db()`, remove the redundant `conn.close()` call at line 378:
```python
# Remove this line (conn.close() inside a with block):
conn.close()
```

**Step 3: Run tests**

Run: `uv run pytest tests/ -v -x`
Expected: All tests pass

---

### Task 3: Fix crawl.py — robots.txt fetch timeout (Important #7)

**Files:**
- Modify: `src/par_scrape/crawl.py`

**Step 1: Add urllib.request import**

Add `import urllib.request` to the imports section (it's already there via `import urllib.robotparser`, but `urllib.request` needs to be explicit).

**Step 2: Replace `rp.read()` with timeout-aware fetch**

In `check_robots_txt()`, replace:
```python
rp.set_url(robots_url)
try:
    rp.read()
    ROBOTS_PARSERS[domain] = rp
except Exception:
    ...
```
With:
```python
rp.set_url(robots_url)
try:
    with urllib.request.urlopen(robots_url, timeout=10) as response:
        rp.parse(line.decode("utf-8", errors="replace") for line in response)
    ROBOTS_PARSERS[domain] = rp
except Exception:
    ...
```

**Step 3: Run tests**

Run: `uv run pytest tests/ -v -x`
Expected: All tests pass

---

### Task 4: Fix __main__.py — assert as control flow (Critical #2)

**Files:**
- Modify: `src/par_scrape/__main__.py`

**Step 1: Replace assert with explicit RuntimeError**

At line 533, change:
```python
assert dynamic_model_container and llm_config
```
To:
```python
if dynamic_model_container is None or llm_config is None:
    raise RuntimeError("LLM configuration is required but was not initialized")
```

**Step 2: Run tests**

Run: `uv run pytest tests/ -v -x`
Expected: All tests pass

---

### Task 5: Fix __main__.py — file_paths lookup type mismatch (Critical #3)

**Files:**
- Modify: `src/par_scrape/__main__.py`

**Step 1: Fix display_output key lookup**

At lines 566-568, change:
```python
if display_output.value in file_paths:
    try:
        content = file_paths[display_output.value].read_text(encoding="utf-8")
```
To:
```python
if display_output in file_paths:
    try:
        content = file_paths[display_output].read_text(encoding="utf-8")
```

**Step 2: Run ruff and tests**

Run: `uv run ruff check src/par_scrape/__main__.py && uv run pytest tests/ -v -x`
Expected: No errors

---

### Task 6: Fix __main__.py — os.path.exists → Path.exists() (Important #5)

**Files:**
- Modify: `src/par_scrape/__main__.py`

**Step 1: Fix line 402 (before cleanup)**

Change:
```python
if os.path.exists(output_folder):
    shutil.rmtree(output_folder)
```
To:
```python
if output_folder.exists():
    shutil.rmtree(output_folder)
```

**Step 2: Fix line 663 (after cleanup)**

Change:
```python
if os.path.exists(output_folder):
    shutil.rmtree(output_folder)
```
To:
```python
if output_folder.exists():
    shutil.rmtree(output_folder)
```

**Step 3: Remove unused `import os` if it's no longer needed**

Check if `os` is used elsewhere in the file. If only for `os.environ.get()`, keep it. Otherwise remove it.

**Step 4: Run ruff and tests**

Run: `uv run ruff check src/par_scrape/__main__.py && uv run pytest tests/ -v -x`
Expected: No PTH110 errors

---

### Task 7: Fix __main__.py — hardcoded output folder (Important #8)

**Files:**
- Modify: `src/par_scrape/__main__.py`

**Step 1: Replace hardcoded Path("./output") with output_folder variable**

At line 413, change:
```python
base_output_folder = Path("./output")
```
To:
```python
base_output_folder = output_folder
```

**Step 2: Run tests**

Run: `uv run pytest tests/ -v -x`
Expected: All tests pass

---

### Task 8: Fix scrape_data.py — missing encoding and os.makedirs (Important #4 & #5)

**Files:**
- Modify: `src/par_scrape/scrape_data.py`

**Step 1: Add encoding to write_text**

At line 34, change:
```python
raw_output_path.write_text(raw_data)
```
To:
```python
raw_output_path.write_text(raw_data, encoding="utf-8")
```

**Step 2: Replace os.makedirs with Path.mkdir**

At line 153, change:
```python
os.makedirs(output_folder, exist_ok=True)
```
To:
```python
output_folder.mkdir(parents=True, exist_ok=True)
```

**Step 3: Remove unused `import os` if no longer needed**

Check if `os` is still used elsewhere in `scrape_data.py`. If not, remove the import.

**Step 4: Run ruff and tests**

Run: `uv run ruff check src/par_scrape/scrape_data.py && uv run pytest tests/ -v -x`
Expected: No PTH errors, all tests pass

---

### Task 9: Replace strenum with stdlib enum.StrEnum (Suggestion #13)

**Files:**
- Modify: `src/par_scrape/enums.py`
- Modify: `pyproject.toml`

**Step 1: Update enums.py**

Change:
```python
from strenum import StrEnum
```
To:
```python
from enum import StrEnum
```

**Step 2: Remove strenum from pyproject.toml**

Remove the line:
```
"strenum>=0.4.15",
```
from the `dependencies` list.

**Step 3: Run uv sync to update lockfile**

Run: `uv sync`

**Step 4: Run tests**

Run: `uv run pytest tests/ -v -x`
Expected: All tests pass

---

### Task 10: Fix config file version inconsistencies (Suggestion #11)

**Files:**
- Modify: `ruff.toml`
- Modify: `pyrightconfig.json`

**Step 1: Update ruff.toml target-version**

Change:
```toml
# Assume Python 3.12
target-version = "py312"
```
To:
```toml
# Assume Python 3.11 (matches requires-python = ">=3.11")
target-version = "py311"
```

**Step 2: Update pyrightconfig.json**

Change `pythonVersion` from `"3.13"` to `"3.14"` and `typeCheckingMode` from `"basic"` to `"standard"` to match `pyproject.toml`:
```json
{
  "pythonVersion": "3.14",
  "typeCheckingMode": "standard"
}
```

**Step 3: Run typecheck**

Run: `uv run pyright`
Expected: 0 errors

---

### Task 11: Fix Makefile — add test and fmt targets (Important #10)

**Files:**
- Modify: `Makefile`

**Step 1: Add fmt alias and test target**

Add after the `format` target:
```makefile
.PHONY: fmt
fmt: format                     # Alias for format (standard convention)

.PHONY: test
test:                           # Run tests with pytest
	$(run) pytest
```

**Step 2: Update checkall to include tests**

Change:
```makefile
checkall: format lint typecheck
```
To:
```makefile
checkall: format lint typecheck test
```

**Step 3: Verify**

Run: `make test`
Expected: pytest output with all tests passing

---

### Task 12: Fix test_crawl.py — inconsistent test param (Suggestion #14)

**Files:**
- Modify: `tests/test_crawl.py`

**Step 1: Fix the empty string param**

At line 91, change the `single_page_no_robots` param:
```python
pytest.param("<a href='/page1'>link</a>", "http://example.com", CrawlType.SINGLE_PAGE, "", False, "", id="single_page_no_robots"),
```
To:
```python
pytest.param("<a href='/page1'>link</a>", "http://example.com", CrawlType.SINGLE_PAGE, "", False, [], id="single_page_no_robots"),
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_crawl.py -v`
Expected: All tests pass

---

### Task 13: Final verification — run make checkall

**Step 1: Run full check**

Run: `make checkall`
Expected: format, lint, typecheck, and test all pass with 0 errors

**Step 2: Commit all changes**

```bash
git add -A
git commit -m "fix: address all code review issues from v0.9.0 review"
```
