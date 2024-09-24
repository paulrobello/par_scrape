"""Enum for scraper choices."""

from enum import Enum


class CleanupType(str, Enum):
    """Enum for cleanup choices."""

    NONE = "none"
    BEFORE = "before"
    AFTER = "after"
    BOTH = "both"


class DisplayOutputFormat(str, Enum):
    """Enum for display output format choices."""

    MD = "md"
    CSV = "csv"
    JSON = "json"


class ScraperChoice(str, Enum):
    """Enum for scraper choices."""

    SELENIUM = "selenium"
    PLAYWRIGHT = "playwright"


class WaitType(str, Enum):
    """Enum for wait type choices."""

    NONE = "none"
    PAUSE = "pause"
    SLEEP = "sleep"
    IDLE = "idle"
    SELECTOR = "selector"
    TEXT = "text"
