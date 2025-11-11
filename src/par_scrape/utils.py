from urllib.parse import urlparse
from par_scrape.exceptions import CrawlConfigError


def normalize_url(url: str) -> str:
    """
    Normalize URLs to a consistent format (e.g., remove trailing slashes).
    Raises CrawlConfigError if the URL is invalid or empty.
    """
    if not url:
        raise CrawlConfigError("URL cannot be empty.")
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise CrawlConfigError(f"Invalid URL: {url}")
    return url.rstrip("/")


def extract_domain(url: str) -> str:
    """
    Extract the domain (netloc) from a URL.
    Raises CrawlConfigError for invalid URLs.
    """
    parsed = urlparse(url)
    if not parsed.netloc:
        raise CrawlConfigError(f"Invalid URL: {url}")
    return parsed.netloc


def chunk_list(items: list, chunk_size: int) -> list[list]:
    """
    Split a list into evenly sized chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def safe_divide(a: float, b: float) -> float:
    """
    Divide two numbers safely, returning 0 if division by zero occurs.
    """
    try:
        return a / b
    except ZeroDivisionError:
        return 0.0


def merge_dicts(a: dict, b: dict) -> dict:
    """
    Merge two dictionaries, with b overwriting keys from a.
    """
    return {**a, **b}
