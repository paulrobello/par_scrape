"""Web crawling functionality for par_scrape."""

import sqlite3
import threading
import time
import urllib.robotparser
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from par_ai_core.web_tools import normalize_url
from rich.console import Console

from par_scrape.enums import OutputFormat
from par_scrape.exceptions import RobotError


def clean_url_of_ticket_id(url: str, ticket_id: str) -> str:
    """
    Clean a URL of any occurrences of the ticket_id to prevent nesting issues.

    Args:
        url: The URL to clean
        ticket_id: The ticket_id to remove from the URL

    Returns:
        str: The cleaned URL
    """
    # Skip if URL is not valid
    if not is_valid_url(url):
        return url

    # Parse the URL
    parsed = urlparse(url)

    # Clean the path of ticket_id - aggressively remove ALL instances
    path_parts = parsed.path.split("/")
    cleaned_parts = []

    for part in path_parts:
        # Skip empty parts and parts that match ticket_id
        if part != "" and part != ticket_id:
            cleaned_parts.append(part)

    # Rebuild path with cleaned parts
    cleaned_path = "/" + "/".join(cleaned_parts)

    # Also clean query parameters if they contain the ticket_id
    query = parsed.query
    if ticket_id in query:
        query_pairs = query.split("&")
        cleaned_query_pairs = []

        for pair in query_pairs:
            if ticket_id not in pair:
                cleaned_query_pairs.append(pair)

        query = "&".join(cleaned_query_pairs)

    # Rebuild the URL with cleaned path and query
    cleaned_parsed = parsed._replace(path=cleaned_path, query=query)
    cleaned_url = cleaned_parsed.geturl()

    return cleaned_url


# from tldextract import tldextract

BASE_PATH = Path("~/.par_scrape").expanduser()
# BASE_PATH = Path(__file__).parent  # debug path
DB_PATH = BASE_PATH / "jobs.sqlite"
# PAGES_BASE = BASE_PATH / "pages"

# Global dictionary to store robots.txt parsers by domain
ROBOTS_PARSERS: dict[str, urllib.robotparser.RobotFileParser] = {}
# Lock for thread-safe access to ROBOTS_PARSERS
ROBOTS_PARSERS_LOCK = threading.Lock()
# Set of excluded URL patterns (common non-content URLs)
EXCLUDED_URL_PATTERNS = {
    "/login",
    "/logout",
    "/signin",
    "/signout",
    "/register",
    "/password",
    "/cart",
    "/checkout",
    "/search",
    "/cdn-cgi/",
    "/wp-admin/",
    "/wp-login.php",
    "/favicon.ico",
    "/sitemap.xml",
    "/robots.txt",
    "/feed",
    "/rss",
    "/comments",
}
# Default user agent for robots.txt
DEFAULT_USER_AGENT = "par-scrape/1.0 (+https://github.com/paulrobello/par_scrape)"


class CrawlType(str, Enum):
    """Types of web crawling strategies."""

    SINGLE_PAGE = "single_page"
    SINGLE_LEVEL = "single_level"
    DOMAIN = "domain"
    # PAGINATED = "paginated"


class PageStatus(str, Enum):
    """Status flags for pages in the crawl queue."""

    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


class ErrorType(str, Enum):
    """Types of errors that can occur during crawling."""

    NETWORK = "network"
    PARSING = "parsing"
    ROBOTS_DISALLOWED = "robots_disallowed"
    INVALID_URL = "invalid_url"
    TIMEOUT = "timeout"
    OTHER = "other"


def is_valid_url(url: str) -> bool:
    """
    Validate if a URL is properly formatted and has a supported scheme.

    Args:
        url: The URL to validate

    Returns:
        bool: True if the URL is valid, False otherwise
    """
    try:
        parsed = urlparse(url)
        return all([parsed.scheme in ("http", "https"), parsed.netloc])
    except Exception:
        return False


def get_url_output_folder(output_path: Path, ticket_id: str, url: str) -> Path:
    """
    Get storage folder based on URL and ticket_id.

    Args:
        output_path: Base path for output files
        ticket_id: Unique identifier for the crawl job
        url: The URL being processed

    Returns:
        Path: The folder path where output for this URL should be stored
    """
    # 1. Start with an absolute base folder - always use "./output"
    base_folder = output_path

    # 2. Add ticket_id once and only once
    run_folder = base_folder / ticket_id

    # 3. Parse the URL without any ticket_id contamination
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.split(":")[0]  # Remove port if present

    # 4. Get path components and aggressively filter out ticket_id
    raw_path = parsed_url.path.strip("/")

    # 5. If there's no path, just use the domain
    if not raw_path:
        return run_folder / domain

    # 6. Create a sanitized path by removing any ticket_id occurrences
    # and converting slashes to double underscores
    path_parts = raw_path.split("/")
    clean_parts = []

    for part in path_parts:
        if part != ticket_id and part != "":
            clean_parts.append(part)

    sanitized_path = "__".join(clean_parts)

    # 7. Final path: ./output/ticket_id/domain/sanitized_path
    if sanitized_path:
        return run_folder / domain / sanitized_path
    else:
        return run_folder / domain


def check_robots_txt(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """
    Check if a URL is allowed by the site's robots.txt.

    Args:
        url: The URL to check
        user_agent: User agent to use for robots.txt checking

    Returns:
        bool: True if the URL is allowed, False if disallowed
    """
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        # Thread-safe access to ROBOTS_PARSERS
        with ROBOTS_PARSERS_LOCK:
            # Get or create a robot parser for this domain
            if domain not in ROBOTS_PARSERS:
                rp = urllib.robotparser.RobotFileParser()
                robots_url = f"{parsed_url.scheme}://{domain}/robots.txt"
                rp.set_url(robots_url)
                try:
                    rp.read()
                    ROBOTS_PARSERS[domain] = rp
                except Exception:
                    # If we can't read robots.txt, assume everything is allowed
                    # Add a placeholder to avoid re-fetching on every request
                    ROBOTS_PARSERS[domain] = rp
                    return True

            # Check if URL is allowed
            return ROBOTS_PARSERS[domain].can_fetch(user_agent, url)
    except Exception:
        # On any failure, default to allowing the URL
        return True


def should_exclude_url(url: str) -> bool:
    """
    Check if a URL should be excluded based on common patterns.

    Args:
        url: The URL to check

    Returns:
        bool: True if the URL should be excluded, False otherwise
    """
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Check for file extensions that aren't likely to be content pages
    if path.endswith(
        (".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".tar.gz", ".css", ".js", ".ico", ".xml", ".json")
    ):
        return True

    # Check for excluded patterns
    for pattern in EXCLUDED_URL_PATTERNS:
        if pattern in path:
            return True

    # URL seems fine
    return False


def extract_links(
    base_url: str,
    html: str,
    crawl_type: CrawlType,
    respect_robots: bool = False,
    console: Console | None = None,
    ticket_id: str = "",
) -> list[str]:
    """
    Extract links from HTML based on crawl type.

    Args:
        base_url: The URL of the page being processed
        html: HTML content of the page
        crawl_type: Type of crawling to perform
        respect_robots: Whether to respect robots.txt
        console: Optional console for logging
        ticket_id: Optional ticket_id to clean from extracted URLs

    Returns:
        list[str]: List of normalized URLs to crawl next
    """
    if crawl_type == CrawlType.SINGLE_PAGE:
        return []

    try:
        soup = BeautifulSoup(html, "html.parser")
        links: set[str] = set()
        base_parsed = urlparse(base_url)

        # Find all link elements
        for link in soup.find_all("a", href=True):
            try:
                # We're using find_all with href=True, so we know href exists
                # Use type: ignore to bypass type checker for BeautifulSoup
                href = str(link["href"])  # type: ignore
                if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                    continue

                # Build absolute URL
                full_url = urljoin(base_url, href)

                # Validate the URL
                if not is_valid_url(full_url):
                    if console:
                        console.print(f"[yellow]Invalid URL: {full_url}[/yellow]")
                    continue

                parsed = urlparse(full_url)

                # Skip fragment-only URLs (same page anchors)
                if parsed.netloc == base_parsed.netloc and not parsed.path and parsed.fragment:
                    continue

                # Apply crawl type filtering
                if (
                    crawl_type == CrawlType.SINGLE_LEVEL or crawl_type == CrawlType.DOMAIN
                ) and parsed.netloc == base_parsed.netloc:
                    # Clean the URL of any ticket_id occurrences first to prevent nesting
                    if ticket_id:
                        full_url = clean_url_of_ticket_id(full_url, ticket_id)

                    normalized_url = normalize_url(full_url)

                    # Skip URLs that match common exclusion patterns
                    if should_exclude_url(normalized_url):
                        continue

                    # Check robots.txt
                    if respect_robots:
                        try:
                            if not check_robots_txt(normalized_url):
                                if console:
                                    console.print(f"[yellow]Skipping disallowed URL: {normalized_url}[/yellow]")
                                continue
                        except RobotError as e:
                            if console:
                                console.print(f"Robots.txt check failed: {str(e)}")
                            continue

                    links.add(normalized_url)
                # PAGINATED crawl type implementation would go here
            except Exception as e:
                if console:
                    console.print(f"[red]Error processing link: {str(e)}[/red]")
                continue

        return list(links)
    except Exception as e:
        if console:
            console.print(f"[red]Error extracting links: {str(e)}[/red]")
        return []


def init_db() -> None:
    """
    Initialize database with required tables.

    Creates the database if it doesn't exist and ensures the schema is up-to-date.
    Checks for version table and removes incompatible databases.
    """
    # Current database schema version
    CURRENT_DB_VERSION = 1

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Check if database exists and if it has our version table
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                # Check if db_version table exists
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'")
                if not cursor.fetchone():
                    # No version table, remove the incompatible database
                    conn.close()
                    DB_PATH.unlink()
                    print(f"Removed incompatible database at {DB_PATH}")
        except sqlite3.Error:
            # If any error occurs, assume the database is corrupted or incompatible
            DB_PATH.unlink()
            print(f"Removed corrupted database at {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
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
        if db_version < CURRENT_DB_VERSION:
            # Create the main scrape table with enhanced fields
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrape (
                    ticket_id TEXT,
                    url TEXT,
                    status TEXT CHECK(status IN ('queued', 'active', 'completed', 'error')) NOT NULL,
                    error_type TEXT,
                    error_msg TEXT,
                    raw_file_path TEXT,
                    md_file_path TEXT,
                    json_file_path TEXT,
                    csv_file_path TEXT,
                    excel_file_path TEXT,
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
                (CURRENT_DB_VERSION, "Initial schema with scrape and domain_rate_limit tables"),
            )


def get_queue_stats(ticket_id: str) -> dict[str, int]:
    """
    Get statistics about the queue for a ticket.

    Args:
        ticket_id: Unique identifier for the crawl job

    Returns:
        dict: Dictionary with counts of items in each status
    """
    with sqlite3.connect(DB_PATH) as conn:
        stats = {}
        for status in PageStatus:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM scrape
                WHERE ticket_id = ? AND status = ?
                """,
                (ticket_id, status.value),
            ).fetchone()
            stats[status.value] = row[0] if row else 0
        return stats


def get_queue_size(ticket_id: str) -> int:
    """
    Get the number of URLs in the queue for a ticket.

    Args:
        ticket_id: Unique identifier for the crawl job

    Returns:
        int: Number of URLs in queued status
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM scrape
            WHERE ticket_id = ? AND status = ?
            """,
            (ticket_id, PageStatus.QUEUED.value),
        ).fetchone()
        return row[0] if row else 0


def add_to_queue(ticket_id: str, urls: Iterable[str], depth: int = 0) -> None:
    """
    Add URLs to queue if they don't already exist.

    Args:
        ticket_id: Unique identifier for the crawl job
        urls: Collection of URLs to add to the queue
        depth: Crawl depth of these URLs (default: 0 for starting URLs)

    Note:
        Invalid URLs are silently skipped and not added to the queue.
        URLs already in error state will have their status reset to QUEUED.
    """

    with sqlite3.connect(DB_PATH) as conn:
        # Use BEGIN IMMEDIATE for better concurrency control
        conn.execute("BEGIN IMMEDIATE")
        try:
            for url in urls:
                # Skip invalid URLs
                if not is_valid_url(url):
                    continue

                # Clean URL of any ticket_id occurrences to prevent nesting
                url = clean_url_of_ticket_id(url, ticket_id)

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
    ticket_id: str, crawl_batch_size: int = 1, scrape_retries: int = 3, respect_rate_limits: bool = True
) -> list[str]:
    """
    Get next batch of URLs to process from the queue, respecting rate limits.

    Args:
        ticket_id: Unique identifier for the crawl job
        crawl_batch_size: Maximum number of URLs to return
        scrape_retries: Maximum number of retry attempts for failed URLs
        respect_rate_limits: Whether to respect per-domain rate limits

    Returns:
        list[str]: List of URLs to process next
    """
    current_time = int(time.time())
    urls = []
    domains_used = set()

    with sqlite3.connect(DB_PATH) as conn:
        # Use BEGIN IMMEDIATE to acquire a write lock immediately and prevent race conditions
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Query includes URLs from each domain respecting rate limits
            if respect_rate_limits:
                # First find eligible domains that respect rate limits
                rows = conn.execute(
                    """
                    SELECT s.url, s.domain, d.last_access, d.crawl_delay
                    FROM scrape s
                    JOIN domain_rate_limit d ON s.domain = d.domain
                    WHERE s.ticket_id = ?
                      AND (s.status = ? OR (s.status = ? AND s.attempts < ?))
                    ORDER BY d.last_access ASC
                    """,
                    (ticket_id, PageStatus.QUEUED.value, PageStatus.ERROR.value, scrape_retries),
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


def set_crawl_delay(domain: str, delay_seconds: int) -> None:
    """
    Set the crawl delay for a specific domain.

    Args:
        domain: Domain to set rate limit for
        delay_seconds: Minimum seconds between requests to this domain
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO domain_rate_limit (domain, last_access, crawl_delay)
            VALUES (?, (SELECT last_access FROM domain_rate_limit WHERE domain = ?), ?)
            """,
            (domain, domain, delay_seconds),
        )


def mark_complete(
    ticket_id: str, url: str, *, raw_file_path: Path, file_paths: dict[OutputFormat, Path], cost: float = 0.0
) -> None:
    """
    Mark URL as successfully scraped.

    Args:
        ticket_id: Unique identifier for the crawl job
        url: URL that was successfully processed
        raw_file_path: Path to the raw output file
        file_paths: Dictionary mapping output formats to file paths
        cost: Cost of processing this URL (if applicable)
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE scrape
            SET status = ?, scraped = strftime('%s','now'), error_msg = null, error_type = null,
            raw_file_path = ?, md_file_path = ?, json_file_path = ?, csv_file_path = ?, excel_file_path = ?,
            cost = ?, last_processed_at = strftime('%s','now')
            WHERE ticket_id = ? AND url = ?
            """,
            (
                PageStatus.COMPLETED.value,
                str(raw_file_path),
                str(file_paths[OutputFormat.MARKDOWN]) if OutputFormat.MARKDOWN in file_paths else None,
                str(file_paths[OutputFormat.JSON]) if OutputFormat.JSON in file_paths else None,
                str(file_paths[OutputFormat.CSV]) if OutputFormat.CSV in file_paths else None,
                str(file_paths[OutputFormat.EXCEL]) if OutputFormat.EXCEL in file_paths else None,
                cost,
                ticket_id,
                url.rstrip("/"),
            ),
        )


def mark_error(
    ticket_id: str, url: str, error_msg: str, error_type: ErrorType = ErrorType.OTHER, cost: float = 0.0
) -> None:
    """
    Mark URL as failed with error message and type.

    Args:
        ticket_id: Unique identifier for the crawl job
        url: URL that failed processing
        error_msg: Error message describing the failure
        error_type: Type of error that occurred
        cost: Cost of processing this URL (if applicable)
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE scrape
            SET status = ?, error_msg = ?, error_type = ?, cost = ?, last_processed_at = strftime('%s','now')
            WHERE ticket_id = ? AND url = ?
            """,
            (PageStatus.ERROR.value, error_msg[:255], error_type.value, cost, ticket_id, url.rstrip("/")),
        )
