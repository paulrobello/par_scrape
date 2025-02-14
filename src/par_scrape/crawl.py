"""Web crawling functionality for par_scrape."""

import sqlite3
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from par_ai_core.web_tools import normalize_url
from tldextract import tldextract

# BASE_PATH = Path("~/.par_scrape").expanduser()
BASE_PATH = Path(__file__).parent  # debug path
DB_PATH = BASE_PATH / "jobs.sqlite"
PAGES_BASE = BASE_PATH / "pages"


class CrawlType(str, Enum):
    SINGLE_PAGE = "single_page"
    SINGLE_LEVEL = "single_level"
    DOMAIN = "domain"
    PAGINATED = "paginated"


class PageStatus(str, Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


def get_url_output_folder(url: str) -> Path:
    """Get storage folder based on URL's top-level domain and page name."""
    extracted = tldextract.extract(url)
    tld = f"{extracted.domain}.{extracted.suffix}"
    return PAGES_BASE / tld.replace(".", "_") / urlparse(url).path.strip("/").replace("/", "_")


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
        elif crawl_type == CrawlType.PAGINATED:
            if "next" in link.get("rel", []) or "page" in link.text.lower():  # type: ignore
                links.append(normalize_url(full_url))

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
                scraped INTEGER,
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
            url = url.rstrip('/')
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


def get_next_url(ticket_id: str) -> str | None:
    """Get next queued URL from database."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT url FROM scrape
            WHERE ticket_id = ? AND status = ?
            LIMIT 1
        """,
            (
                ticket_id,
                PageStatus.QUEUED.value,
            ),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE scrape
            SET status = ?
            WHERE ticket_id = ? AND url = ?
        """,
            (PageStatus.ACTIVE.value, ticket_id, row[0]),
        )
        return row[0]


def mark_complete(ticket_id: str, url: str, cost: float = 0.0) -> None:
    """Mark URL as successfully scraped."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE scrape
            SET status = ?, scraped = strftime('%s','now'), cost = ?
            WHERE ticket_id = ? AND url = ?
        """,
            (PageStatus.COMPLETED.value, cost, ticket_id, url.rstrip('/')),
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
            (PageStatus.ERROR.value, error_msg[:255], cost, ticket_id, url.rstrip('/')),
        )
