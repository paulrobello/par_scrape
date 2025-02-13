"""Enum for scraper choices."""

from strenum import StrEnum


class CleanupType(StrEnum):
    """Enum for cleanup choices."""

    NONE = "none"
    BEFORE = "before"
    AFTER = "after"
    BOTH = "both"
