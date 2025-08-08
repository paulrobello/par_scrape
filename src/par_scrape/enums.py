"""Enums for scraper choices."""

from strenum import StrEnum


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
