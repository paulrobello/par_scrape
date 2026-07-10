"""Shared pytest fixtures for par_scrape tests.

ARC-011 established the canonical ``db_path`` fixture here. It yields a
``tmp_path``-backed SQLite database path, initializes the schema on it via
explicit ``db_path=`` injection, and (for back-compat) also points the
module-level ``queue_db.DB_PATH`` at the same file so code that still reads
the module global keeps working. New tests should prefer explicit
``db_path=`` injection over reading ``DB_PATH``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from par_scrape import queue_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Yield an initialized temp SQLite database path for the crawl queue."""
    path = tmp_path / "test.sqlite"
    queue_db.init_db(db_path=path)
    # Back-compat: tests/code that still read the module global keep working.
    queue_db.DB_PATH = path
    return path
