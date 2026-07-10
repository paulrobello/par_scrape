"""Typed exceptions for par_scrape error classification and retry routing."""

import urllib.error

from par_scrape.enums import ErrorType


class ParScrapeError(Exception):
    """Base exception for all par_scrape errors."""

    pass


class CrawlConfigError(ParScrapeError):
    """Raised when crawl or scrape configuration is invalid."""

    pass


class ProviderConfigError(ParScrapeError):
    """Raised when AI provider or model configuration is invalid."""

    pass


class InvalidURLError(ParScrapeError):
    """Raised when a URL is invalid."""

    pass


class ScrapeError(ParScrapeError):
    """Raised when a scraping operation fails."""

    pass


class RobotError(ParScrapeError):
    """Raised when there is a failure parsing or reading robots.txt."""

    pass


def classify_error(exc: Exception) -> ErrorType:
    """Map an exception to an ErrorType for retry/rate-limit routing.

    Prefers isinstance checks; falls back to message keywords for exceptions
    raised by third-party libraries (e.g. provider SDKs that wrap failures in
    generic ``RuntimeError``/``Exception``).

    Args:
        exc: The exception to classify.

    Returns:
        ErrorType: The categorized error type.
    """
    if isinstance(exc, RobotError):
        return ErrorType.ROBOTS_DISALLOWED
    if isinstance(exc, InvalidURLError):
        return ErrorType.INVALID_URL
    if isinstance(exc, TimeoutError):
        return ErrorType.TIMEOUT
    if isinstance(exc, ConnectionError | urllib.error.URLError):
        return ErrorType.NETWORK
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return ErrorType.TIMEOUT
    if "network" in msg or "connection" in msg:
        return ErrorType.NETWORK
    if "robots.txt" in msg or "disallowed" in msg:
        return ErrorType.ROBOTS_DISALLOWED
    if "html" in msg or "parse" in msg:
        return ErrorType.PARSING
    if "url" in msg or "scheme" in msg:
        return ErrorType.INVALID_URL
    return ErrorType.OTHER
