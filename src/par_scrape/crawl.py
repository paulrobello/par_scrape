"""Web crawling functionality for par_scrape."""

import sqlite3
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from par_ai_core.web_tools import normalize_url

from par_scrape.enums import OutputFormat

# from tldextract import tldextract

BASE_PATH = Path("~/.par_scrape").expanduser()
# BASE_PATH = Path(__file__).parent  # debug path
DB_PATH = BASE_PATH / "jobs.sqlite"
# PAGES_BASE = BASE_PATH / "pages"


class CrawlType(str, Enum):
    SINGLE_PAGE = "single_page"
    SINGLE_LEVEL = "single_level"
    DOMAIN = "domain"
    # PAGINATED = "paginated"


class PageStatus(str, Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


def get_url_output_folder(output_path: Path, ticket_id: str, url: str) -> Path:
    """Get storage folder based on URL and ticket_id."""
    # extracted = tldextract.extract(url)
    # tld = f"{extracted.domain}.{extracted.suffix}".replace(".", "_")
    return output_path / ticket_id / urlparse(url).path.strip("/").replace("/", "__")


def extract_links(base_url: str, html: str, crawl_type: CrawlType) -> list[str]:
    """Extract links from HTML based on crawl type."""
    if crawl_type == CrawlType.SINGLE_PAGE:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for link in soup.find_all("a", href=True):
        href = str(link["href"])  # type: ignore
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if crawl_type == CrawlType.SINGLE_LEVEL:
            if parsed.netloc == urlparse(base_url).netloc:
                links.append(normalize_url(full_url))
        elif crawl_type == CrawlType.DOMAIN:
            if parsed.netloc == urlparse(base_url).netloc:
                links.append(normalize_url(full_url))
        # elif crawl_type == CrawlType.PAGINATED:
        #     if "next" in link.get("rel", []) or "page" in link.text.lower():  # type: ignore
        #         links.append(normalize_url(full_url))

    return list(set(links))


def init_db() -> None:
    """Initialize database with scrape table."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape (
                ticket_id TEXT,
                url TEXT,
                status TEXT CHECK(status IN ('queued', 'active', 'completed', 'error')) NOT NULL,
                error_msg TEXT,
                raw_file_path TEXT,
                md_file_path TEXT,
                json_file_path TEXT,
                csv_file_path TEXT,
                excel_file_path TEXT,
                scraped INTEGER,
                attempts INTEGER DEFAULT 0,
                cost FLOAT,
                PRIMARY KEY (ticket_id, url)
            )
        """)


def get_queue_size(ticket_id: str) -> int:
    """Get the number of URLs in the queue for a ticket."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM scrape
            WHERE ticket_id = ? AND status = ?
        """,
            (ticket_id, PageStatus.QUEUED.value),
        ).fetchone()
        return row[0] if row else 0


def add_to_queue(ticket_id: str, urls: Iterable[str]) -> None:
    """Add URLs to queue if they don't already exist."""
    with sqlite3.connect(DB_PATH) as conn:
        for url in urls:
            url = url.rstrip("/")
            # print(url)
            conn.execute(
                """
                INSERT OR IGNORE INTO scrape (ticket_id, url, status)
                VALUES (?, ?, ?)
            """,
                (ticket_id, url, PageStatus.QUEUED.value),
            )

            # Reset error status if re-adding
            conn.execute(
                """
                UPDATE scrape
                SET status = ?, error_msg = NULL
                WHERE ticket_id = ? AND url = ? AND status = ?
            """,
                (PageStatus.QUEUED.value, ticket_id, url, PageStatus.ERROR.value),
            )


def get_next_urls(ticket_id: str, crawl_batch_size: int = 1, scrape_retries: int = 3) -> list[str]:
    """Get next queued URL from database."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT url FROM scrape
            WHERE ticket_id = ? AND (status = ? or (status = ? AND attempts < ?))
            LIMIT ?
        """,
            (ticket_id, PageStatus.QUEUED.value, PageStatus.ERROR.value, scrape_retries, crawl_batch_size),
        ).fetchall()
        if not rows:
            return []
        urls = [row[0] for row in rows]
        placeholders = ", ".join("?" for _ in urls)
        conn.execute(
            f"""
            UPDATE scrape
            SET status = ?, attempts = attempts + 1
            WHERE ticket_id = ? AND url in ({placeholders})
        """,
            [PageStatus.ACTIVE.value, ticket_id] + urls,
        )
        return urls


def mark_complete(
    ticket_id: str, url: str, *, raw_file_path: Path, file_paths: dict[OutputFormat, Path], cost: float = 0.0
) -> None:
    """Mark URL as successfully scraped."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE scrape
            SET status = ?, scraped = strftime('%s','now'), error_msg = null,
            raw_file_path = ?, md_file_path = ?, json_file_path = ?, csv_file_path = ?, excel_file_path = ?,
            cost = ?
            WHERE ticket_id = ? AND url = ?
        """,
            (
                PageStatus.COMPLETED.value,
                str(raw_file_path),
                str(file_paths[OutputFormat.MARKDOWN]),
                str(file_paths[OutputFormat.JSON]) if OutputFormat.JSON in file_paths else None,
                str(file_paths[OutputFormat.CSV]) if OutputFormat.CSV in file_paths else None,
                str(file_paths[OutputFormat.EXCEL]) if OutputFormat.EXCEL in file_paths else None,
                cost,
                ticket_id,
                url.rstrip("/"),
            ),
        )


def mark_error(ticket_id: str, url: str, error_msg: str, cost: float = 0.0) -> None:
    """Mark URL as failed with error message."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE scrape
            SET status = ?, error_msg = ?, cost = ?
            WHERE ticket_id = ? AND url = ?
        """,
            (PageStatus.ERROR.value, error_msg[:255], cost, ticket_id, url.rstrip("/")),
        )
