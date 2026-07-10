"""Enums for scraper choices."""

from enum import StrEnum


class CleanupType(StrEnum):
    """Enum for cleanup choices."""

    NONE = "none"
    BEFORE = "before"
    AFTER = "after"
    BOTH = "both"


class OutputFormat(StrEnum):
    """Enum for output formats."""

    MARKDOWN = "md"
    JSON = "json"
    CSV = "csv"
    EXCEL = "excel"


class CrawlType(StrEnum):
    """Types of web crawling strategies."""

    SINGLE_PAGE = "single_page"
    SINGLE_LEVEL = "single_level"
    DOMAIN = "domain"
    # PAGINATED = "paginated"


class PageStatus(StrEnum):
    """Status flags for pages in the crawl queue."""

    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


class ErrorType(StrEnum):
    """Types of errors that can occur during crawling.

    Lives in ``enums`` (not ``crawl``) so that ``exceptions.classify_error``
    can import it without creating a circular import (``crawl`` imports from
    ``exceptions``). ``crawl`` re-exports it for backwards compatibility.
    """

    NETWORK = "network"
    PARSING = "parsing"
    ROBOTS_DISALLOWED = "robots_disallowed"
    INVALID_URL = "invalid_url"
    TIMEOUT = "timeout"
    OTHER = "other"
