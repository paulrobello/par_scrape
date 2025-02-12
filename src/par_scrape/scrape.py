"""Web crawling functionality for par_scrape."""

import sqlite3
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from tldextract import tldextract

DB_PATH = Path("~/.par_scrape/jobs.sqlite").expanduser()
PAGES_BASE = Path("~/.par_scrape/pages").expanduser()

class ScrapeType(str, Enum):
    SINGLE_LEVEL = "single_level"
    DOMAIN = "domain"
    PAGINATED = "paginated"

class PageStatus(str, Enum):
    QUEUED = "queued"
    COMPLETED = "completed"
    ERROR = "error"

def init_db() -> None:
    """Initialize database with scrape table."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape (
                url TEXT PRIMARY KEY,
                status TEXT CHECK(status IN ('queued', 'completed', 'error')) NOT NULL,
                error_msg TEXT,
                scraped INTEGER
            )
        """)

def add_to_queue(urls: Iterable[str]) -> None:
    """Add URLs to queue if they don't already exist."""
    with sqlite3.connect(DB_PATH) as conn:
        for url in urls:
            conn.execute("""
                INSERT OR IGNORE INTO scrape (url, status) 
                VALUES (?, ?)
            """, (url, PageStatus.QUEUED.value))

            # Reset error status if re-adding
            conn.execute("""
                UPDATE scrape 
                SET status = ?, error_msg = NULL 
                WHERE url = ? AND status = ?
            """, (PageStatus.QUEUED.value, url, PageStatus.ERROR.value))

def get_tld_folder(url: str) -> Path:
    """Get storage folder based on URL's top-level domain."""
    extracted = tldextract.extract(url)
    tld = f"{extracted.domain}.{extracted.suffix}"
    return PAGES_BASE / tld.replace(".", "_")

def extract_links(base_url: str, html: str, scrape_type: ScrapeType) -> list[str]:
    """Extract links from HTML based on crawl type."""
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if scrape_type == ScrapeType.SINGLE_LEVEL:
            if parsed.netloc == urlparse(base_url).netloc:
                links.append(full_url)
        elif scrape_type == ScrapeType.DOMAIN:
            if parsed.netloc == urlparse(base_url).netloc:
                links.append(full_url)
        elif scrape_type == ScrapeType.PAGINATED:
            if "next" in link.get("rel", []) or "page" in link.text.lower():
                links.append(full_url)

    return list(set(links))

def get_next_url() -> str | None:
    """Get next queued URL from database."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
            SELECT url FROM scrape 
            WHERE status = ? 
            LIMIT 1
        """, (PageStatus.QUEUED.value,)).fetchone()
        return row[0] if row else None

def mark_complete(url: str) -> None:
    """Mark URL as successfully scraped."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE scrape 
            SET status = ?, scraped = strftime('%s','now') 
            WHERE url = ?
        """, (PageStatus.COMPLETED.value, url))

def mark_error(url: str, error_msg: str) -> None:
    """Mark URL as failed with error message."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE scrape 
            SET status = ?, error_msg = ? 
            WHERE url = ?
        """, (PageStatus.ERROR.value, error_msg[:255], url))
