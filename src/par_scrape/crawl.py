"""Backwards-compatibility shim for the former monolithic ``crawl`` module.

ARC-008 split this module into single-concern modules:

- ``par_scrape.queue_db`` — SQLite-backed crawl queue (persistence layer).
- ``par_scrape.robots`` — robots.txt fetching and fetch policy.
- ``par_scrape.links`` — link extraction and URL filtering.
- ``par_scrape.paths`` — output path computation for crawled URLs.

All names below are re-exported so existing callers (``runner.py``,
``__main__.py``, and ``tests/test_crawl.py``) keep working unchanged. New
code should import from the specific module instead of ``par_scrape.crawl``.

Note: the queue functions in ``queue_db`` read their own module global
``queue_db.DB_PATH``. Tests that redirect the database must patch
``par_scrape.queue_db.DB_PATH`` (not ``crawl.DB_PATH``); see ARC-011 for the
upcoming injectable ``db_path`` parameter.
"""

from par_scrape.enums import CrawlType, ErrorType, OutputFormat, PageStatus
from par_scrape.links import (
    EXCLUDED_URL_PATTERNS,
    extract_links,
    is_valid_url,
    should_exclude_url,
)
from par_scrape.paths import get_url_output_folder
from par_scrape.queue_db import (
    BASE_PATH,
    DB_PATH,
    add_to_queue,
    delete_run,
    find_completed_by_hash,
    get_next_urls,
    get_queue_stats,
    get_run_pages,
    get_url_depth,
    increase_crawl_delay,
    init_db,
    list_runs,
    mark_complete,
    mark_error,
    requeue_errors,
    set_crawl_delay,
)
from par_scrape.robots import (
    DEFAULT_USER_AGENT,
    ROBOTS_PARSERS,
    ROBOTS_PARSERS_LOCK,
    check_robots_txt,
)

__all__ = [
    # enums
    "CrawlType",
    "PageStatus",
    "ErrorType",
    "OutputFormat",
    # queue_db (persistence)
    "BASE_PATH",
    "DB_PATH",
    "init_db",
    "add_to_queue",
    "delete_run",
    "find_completed_by_hash",
    "get_next_urls",
    "get_queue_stats",
    "get_run_pages",
    "get_url_depth",
    "increase_crawl_delay",
    "list_runs",
    "mark_complete",
    "mark_error",
    "requeue_errors",
    "set_crawl_delay",
    # robots
    "ROBOTS_PARSERS",
    "ROBOTS_PARSERS_LOCK",
    "DEFAULT_USER_AGENT",
    "check_robots_txt",
    # links
    "EXCLUDED_URL_PATTERNS",
    "extract_links",
    "should_exclude_url",
    "is_valid_url",
    # paths
    "get_url_output_folder",
]
