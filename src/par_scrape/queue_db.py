"""SQLite-backed crawl queue (persistence / repository layer)."""

import json
import sqlite3
import threading
import time
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

from par_ai_core.par_logging import console_out
from par_ai_core.web_tools import normalize_url

from par_scrape.enums import ErrorType, OutputFormat, PageStatus
from par_scrape.links import is_valid_url

BASE_PATH = Path("~/.par_scrape").expanduser()
DB_PATH = BASE_PATH / "jobs.sqlite"

# Current database schema version. Bumping this causes an existing, older
# database to be moved aside (see ``_rename_db_aside``) rather than silently
# recreated, so the user's crawl history is never lost on upgrade.
DB_VERSION = 2

# Maximum characters of an error message persisted to the scrape table; keeps
# the error_msg column bounded on pathological failures. See ``mark_error``.
ERROR_MESSAGE_MAX_LEN = 255

# Per-thread cache of long-lived SQLite connections. SQLite connections are not
# safe to share across threads, so the cache lives on a threading.local and is
# keyed by resolved database path. See ``_get_connection``.
_local = threading.local()


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a cached per-thread SQLite connection configured for WAL.

    Replaces the former connection-per-statement pattern. Each connection is
    opened once with ``busy_timeout=5000`` (wait rather than raise ``database
    is locked``), ``synchronous=NORMAL``, and ``journal_mode=WAL`` so concurrent
    readers/writers are safe — a prerequisite for the thread pool in ENH-001.
    WAL is rejected on some network filesystems (e.g. NFS); in that case the
    busy timeout still applies and the database keeps its default journal mode.

    Args:
        db_path: Database file to open. Defaults to :data:`DB_PATH` when ``None``
            (resolved at call time so tests can patch ``DB_PATH``).

    Returns:
        A long-lived connection for ``(this thread, resolved path)``. Callers own
        the transaction scope via ``with conn:``; the connection itself is reused
        across calls and released by :func:`close_connections`.
    """
    path = Path(db_path) if db_path is not None else DB_PATH
    cache: dict[str, sqlite3.Connection] = getattr(_local, "connections", None) or {}
    _local.connections = cache
    key = str(path.resolve())
    conn = cache.get(key)
    if conn is None:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        # WAL may be unsupported on network filesystems; fall back silently.
        conn.execute("PRAGMA journal_mode=WAL")
        cache[key] = conn
    return conn


def close_connections() -> None:
    """Close this thread's cached SQLite connections.

    Called from the runner's ``finally`` block on shutdown and from the test
    fixture teardown so cached connections do not leak as ``ResourceWarning``
    (this project has history there; see commit ``7a1e003``).
    """
    cache: dict[str, sqlite3.Connection] = getattr(_local, "connections", None) or {}
    for conn in cache.values():
        try:
            conn.close()
        except sqlite3.Error:
            pass
    cache.clear()


def _rename_db_aside(found_version: int | None, db_path: Path) -> None:
    """
    Move an incompatible database file aside instead of deleting it (ARC-009).

    Renames ``db_path`` to ``<name>.bak-v<version>`` (or ``.bak-vunknown`` when
    the version could not be determined). If a backup with that name already
    exists, appends ``.1``, ``.2``, ... so prior backups are never overwritten.

    Args:
        found_version: The schema version discovered in the existing database,
            or ``None`` when the version table was missing/unreadable.
        db_path: Database file to move aside.
    """
    version_label = found_version if found_version is not None else "unknown"
    base_name = f"{db_path.name}.bak-v{version_label}"
    backup = db_path.with_name(base_name)
    counter = 1
    while backup.exists():
        backup = db_path.with_name(f"{base_name}.{counter}")
        counter += 1
    # Drop WAL sidecar files alongside the main database; under WAL mode the
    # main file's -wal/-shm siblings are transient checkpoint artifacts and must
    # not be left orphaned when the database is moved aside.
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            sidecar.unlink()
    db_path.rename(backup)
    console_out.print(
        f"[bold yellow]Incompatible crawl database moved to {backup}. "
        f"A fresh database was created; delete the backup when no longer needed.[/bold yellow]"
    )


def init_db(db_path: Path | None = None) -> None:
    """
    Initialize database with required tables.

    Creates the database if it doesn't exist. When an existing database is
    incompatible (missing ``db_version`` table, unreadable, or at an older
    schema version than :data:`DB_VERSION`) it is renamed aside via
    :func:`_rename_db_aside` rather than deleted, so crawl history survives an
    upgrade. A fresh schema is then created.

    Args:
        db_path: Database file to initialize. Defaults to :data:`DB_PATH` when
            ``None`` (resolved at call time so tests can patch ``DB_PATH``).
    """
    db_path = db_path if db_path is not None else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    found_version: int | None = None
    rebuild = False
    if db_path.exists():
        try:
            with closing(sqlite3.connect(db_path)) as conn, conn:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'")
                if cursor.fetchone():
                    row = conn.execute("SELECT version FROM db_version ORDER BY version DESC LIMIT 1").fetchone()
                    version = int(row[0]) if row else 0
                    found_version = version
                    rebuild = version < DB_VERSION
                else:
                    # No version table: pre-versioning (or foreign) database.
                    rebuild = True
        except sqlite3.Error:
            # Corrupted or otherwise unreadable database.
            rebuild = True

        if rebuild:
            # Release any cached handles on this thread before moving the file
            # aside — cached connections are long-lived (see ``_get_connection``).
            close_connections()
            _rename_db_aside(found_version, db_path)

    with closing(sqlite3.connect(db_path)) as conn, conn:
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        # Create version tracking table first
        conn.execute("""
            CREATE TABLE IF NOT EXISTS db_version (
                version INTEGER PRIMARY KEY,
                created_at INTEGER DEFAULT (strftime('%s','now')),
                description TEXT
            )
        """)

        # Check current version
        cursor = conn.execute("SELECT version FROM db_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        db_version = row[0] if row else 0

        # If database is outdated, update schema as needed
        if db_version < DB_VERSION:
            # Create the main scrape table with enhanced fields
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrape (
                    ticket_id TEXT,
                    url TEXT,
                    status TEXT CHECK(status IN ('queued', 'active', 'completed', 'error')) NOT NULL,
                    error_type TEXT,
                    error_msg TEXT,
                    raw_file_path TEXT,
                    file_paths TEXT,
                    scraped INTEGER,
                    queued_at INTEGER DEFAULT (strftime('%s','now')),
                    last_processed_at INTEGER,
                    attempts INTEGER DEFAULT 0,
                    cost FLOAT,
                    domain TEXT,
                    depth INTEGER DEFAULT 0,
                    PRIMARY KEY (ticket_id, url)
                )
            """)

            # Create domain rate limiting table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS domain_rate_limit (
                    domain TEXT PRIMARY KEY,
                    last_access INTEGER,
                    crawl_delay INTEGER DEFAULT 1
                )
            """)

            # Create an index on status for faster querying
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON scrape(status, ticket_id)
            """)

            # Create an index on domain for faster rate limit lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_domain ON scrape(domain)
            """)

            # Update version information
            conn.execute(
                """
                INSERT INTO db_version (version, description)
                VALUES (?, ?)
                """,
                (DB_VERSION, "Schema v2: per-format path columns collapsed into file_paths JSON"),
            )


def get_queue_stats(ticket_id: str, db_path: Path | None = None) -> dict[str, int]:
    """
    Get statistics about the queue for a ticket.

    Args:
        ticket_id: Unique identifier for the crawl job
        db_path: Database file to query. Defaults to :data:`DB_PATH` when ``None``.

    Returns:
        dict: Dictionary with counts of items in each status
    """
    db_path = db_path if db_path is not None else DB_PATH
    conn = _get_connection(db_path)
    with conn:
        # One indexed scan with GROUP BY instead of four COUNT(*) queries; the
        # dict is pre-filled so callers always see every PageStatus (zero-count
        # statuses that have no rows still appear).
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM scrape WHERE ticket_id = ? GROUP BY status", (ticket_id,)
        ).fetchall()
        stats = {status.value: 0 for status in PageStatus}
        for status_value, count in rows:
            stats[status_value] = count
        return stats


def add_to_queue(ticket_id: str, urls: Iterable[str], depth: int = 0, db_path: Path | None = None) -> None:
    """
    Add URLs to queue if they don't already exist.

    Args:
        ticket_id: Unique identifier for the crawl job
        urls: Collection of URLs to add to the queue
        depth: Crawl depth of these URLs (default: 0 for starting URLs)
        db_path: Database file to write to. Defaults to :data:`DB_PATH` when ``None``.

    Note:
        Invalid URLs are silently skipped and not added to the queue.
        URLs already in error state will have their status reset to QUEUED.
    """
    db_path = db_path if db_path is not None else DB_PATH

    conn = _get_connection(db_path)
    with conn:
        # Use BEGIN IMMEDIATE for better concurrency control
        conn.execute("BEGIN IMMEDIATE")
        try:
            for url in urls:
                # Skip invalid URLs
                if not is_valid_url(url):
                    continue

                # Normalize URL before adding
                url = normalize_url(url.rstrip("/"))
                parsed = urlparse(url)
                domain = parsed.netloc

                # Insert new URL or ignore if it exists
                conn.execute(
                    """
                    INSERT OR IGNORE INTO scrape
                    (ticket_id, url, status, domain, depth, queued_at)
                    VALUES (?, ?, ?, ?, ?, strftime('%s','now'))
                    """,
                    (ticket_id, url, PageStatus.QUEUED.value, domain, depth),
                )

                # Reset error status if re-adding
                conn.execute(
                    """
                    UPDATE scrape
                    SET status = ?, error_msg = NULL, error_type = NULL
                    WHERE ticket_id = ? AND url = ? AND status = ?
                    """,
                    (PageStatus.QUEUED.value, ticket_id, url, PageStatus.ERROR.value),
                )

                # Ensure domain exists in rate limit table
                conn.execute(
                    """
                    INSERT OR IGNORE INTO domain_rate_limit (domain, last_access, crawl_delay)
                    VALUES (?, 0, 1)
                    """,
                    (domain,),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_next_urls(
    ticket_id: str,
    crawl_batch_size: int = 1,
    scrape_retries: int = 3,
    respect_rate_limits: bool = True,
    db_path: Path | None = None,
) -> list[str]:
    """
    Get next batch of URLs to process from the queue, respecting rate limits.

    Args:
        ticket_id: Unique identifier for the crawl job
        crawl_batch_size: Maximum number of URLs to return
        scrape_retries: Maximum number of retry attempts for failed URLs
        respect_rate_limits: Whether to respect per-domain rate limits
        db_path: Database file to query. Defaults to :data:`DB_PATH` when ``None``.

    Returns:
        list[str]: List of URLs to process next
    """
    db_path = db_path if db_path is not None else DB_PATH
    current_time = int(time.time())
    urls = []
    domains_used = set()

    conn = _get_connection(db_path)
    with conn:
        # Use BEGIN IMMEDIATE to acquire a write lock immediately and prevent race conditions
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Query includes URLs from each domain respecting rate limits
            if respect_rate_limits:
                # Candidate pool well above batch_size because rate-limit filtering
                # happens in Python after the query (many candidates may share one
                # rate-limited domain and get skipped before the batch fills).
                candidate_pool = max(crawl_batch_size * 25, 100)
                # First find eligible domains that respect rate limits
                rows = conn.execute(
                    """
                    SELECT s.url, s.domain, d.last_access, d.crawl_delay
                    FROM scrape s
                    JOIN domain_rate_limit d ON s.domain = d.domain
                    WHERE s.ticket_id = ?
                      AND (s.status = ? OR (s.status = ? AND s.attempts < ?))
                    ORDER BY d.last_access ASC
                    LIMIT ?
                    """,
                    (ticket_id, PageStatus.QUEUED.value, PageStatus.ERROR.value, scrape_retries, candidate_pool),
                ).fetchall()

                # Process each row, respecting rate limits
                for row in rows:
                    url, domain, last_access, crawl_delay = row

                    # Skip if we already have a URL from this domain in the batch
                    if domain in domains_used:
                        continue

                    # Skip if rate limit not elapsed
                    if last_access > 0 and current_time - last_access < crawl_delay:
                        continue

                    # Add URL to batch
                    urls.append(url)
                    domains_used.add(domain)

                    # Update last access time for this domain
                    conn.execute(
                        """
                        UPDATE domain_rate_limit
                        SET last_access = ?
                        WHERE domain = ?
                        """,
                        (current_time, domain),
                    )

                    # Stop if we have enough URLs
                    if len(urls) >= crawl_batch_size:
                        break
            else:
                # Simple version that doesn't respect rate limits
                rows = conn.execute(
                    """
                    SELECT url FROM scrape
                    WHERE ticket_id = ? AND (status = ? OR (status = ? AND attempts < ?))
                    LIMIT ?
                    """,
                    (ticket_id, PageStatus.QUEUED.value, PageStatus.ERROR.value, scrape_retries, crawl_batch_size),
                ).fetchall()
                urls = [row[0] for row in rows]

            # Mark selected URLs as active
            if urls:
                placeholders = ", ".join("?" for _ in urls)
                conn.execute(
                    f"""
                    UPDATE scrape
                    SET status = ?, attempts = attempts + 1, last_processed_at = strftime('%s','now')
                    WHERE ticket_id = ? AND url IN ({placeholders})
                    """,
                    [PageStatus.ACTIVE.value, ticket_id] + urls,
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return urls


def set_crawl_delay(domain: str, delay_seconds: int, db_path: Path | None = None) -> None:
    """
    Set the crawl delay for a specific domain.

    Args:
        domain: Domain to set rate limit for
        delay_seconds: Minimum seconds between requests to this domain
        db_path: Database file to write to. Defaults to :data:`DB_PATH` when ``None``.
    """
    db_path = db_path if db_path is not None else DB_PATH
    conn = _get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO domain_rate_limit (domain, last_access, crawl_delay)
            VALUES (?, (SELECT last_access FROM domain_rate_limit WHERE domain = ?), ?)
            """,
            (domain, domain, delay_seconds),
        )


def get_url_depth(ticket_id: str, url: str, db_path: Path | None = None) -> int:
    """
    Get the crawl depth recorded for a queued URL.

    Args:
        ticket_id: Unique identifier for the crawl job
        url: URL whose stored depth is being queried
        db_path: Database file to query. Defaults to :data:`DB_PATH` when ``None``.

    Returns:
        int: The row's ``depth`` value, or ``0`` when the URL is not queued
    """
    db_path = db_path if db_path is not None else DB_PATH
    conn = _get_connection(db_path)
    with conn:
        row = conn.execute(
            "SELECT depth FROM scrape WHERE ticket_id = ? AND url = ?",
            (ticket_id, url.rstrip("/")),
        ).fetchone()
        return row[0] if row else 0


def increase_crawl_delay(domain: str, factor: int = 2, cap: int = 30, db_path: Path | None = None) -> int:
    """
    Multiply a domain's crawl delay by ``factor``, capped at ``cap`` seconds.

    Reads the current delay (defaulting to ``1`` when the domain is unknown),
    computes ``min(current * factor, cap)``, persists it via
    :func:`set_crawl_delay`, and returns the new value. Used for adaptive
    backoff on network/timeout failures.

    Args:
        domain: Domain whose rate limit should be increased
        factor: Multiplier applied to the current delay (default: 2)
        cap: Upper bound in seconds for the new delay (default: 30)
        db_path: Database file to read/write. Defaults to :data:`DB_PATH` when ``None``.

    Returns:
        int: The new crawl delay in effect for ``domain``
    """
    db_path = db_path if db_path is not None else DB_PATH
    conn = _get_connection(db_path)
    with conn:
        row = conn.execute("SELECT crawl_delay FROM domain_rate_limit WHERE domain = ?", (domain,)).fetchone()
        current_delay = row[0] if row else 1
    new_delay = min(current_delay * factor, cap)
    set_crawl_delay(domain, new_delay, db_path=db_path)
    return new_delay


def mark_complete(
    ticket_id: str,
    url: str,
    *,
    raw_file_path: Path,
    file_paths: dict[OutputFormat, Path],
    cost: float = 0.0,
    db_path: Path | None = None,
) -> None:
    """
    Mark URL as successfully scraped.

    Args:
        ticket_id: Unique identifier for the crawl job
        url: URL that was successfully processed
        raw_file_path: Path to the raw output file
        file_paths: Dictionary mapping output formats to file paths
        cost: Cost of processing this URL (if applicable)
        db_path: Database file to write to. Defaults to :data:`DB_PATH` when ``None``.
    """
    db_path = db_path if db_path is not None else DB_PATH
    conn = _get_connection(db_path)
    with conn:
        conn.execute(
            """
            UPDATE scrape
            SET status = ?, scraped = strftime('%s','now'), error_msg = null, error_type = null,
            raw_file_path = ?, file_paths = ?,
            cost = ?, last_processed_at = strftime('%s','now')
            WHERE ticket_id = ? AND url = ?
            """,
            (
                PageStatus.COMPLETED.value,
                str(raw_file_path),
                json.dumps({fmt.value: str(p) for fmt, p in file_paths.items()}, ensure_ascii=False),
                cost,
                ticket_id,
                url.rstrip("/"),
            ),
        )


def mark_error(
    ticket_id: str,
    url: str,
    error_msg: str,
    error_type: ErrorType = ErrorType.OTHER,
    cost: float = 0.0,
    db_path: Path | None = None,
) -> None:
    """
    Mark URL as failed with error message and type.

    Args:
        ticket_id: Unique identifier for the crawl job
        url: URL that failed processing
        error_msg: Error message describing the failure
        error_type: Type of error that occurred
        cost: Cost of processing this URL (if applicable)
        db_path: Database file to write to. Defaults to :data:`DB_PATH` when ``None``.
    """
    db_path = db_path if db_path is not None else DB_PATH
    conn = _get_connection(db_path)
    with conn:
        conn.execute(
            """
            UPDATE scrape
            SET status = ?, error_msg = ?, error_type = ?, cost = ?, last_processed_at = strftime('%s','now')
            WHERE ticket_id = ? AND url = ?
            """,
            (
                PageStatus.ERROR.value,
                error_msg[:ERROR_MESSAGE_MAX_LEN],
                error_type.value,
                cost,
                ticket_id,
                url.rstrip("/"),
            ),
        )
