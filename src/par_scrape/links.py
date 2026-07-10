"""Link extraction and URL filtering for crawling."""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from par_ai_core.web_tools import normalize_url
from rich.console import Console
from rich.markup import escape

from par_scrape.enums import CrawlType
from par_scrape.robots import check_robots_txt

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
    except ValueError:
        # urlparse raises ValueError on malformed URLs; anything else is a bug.
        return False


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

    # Check for excluded patterns, anchored to path segments so that e.g.
    # "/feed" matches "/feed" and "/blog/feed" but not "/feedback" (ARC-019).
    if any(re.search(rf"(^|/){re.escape(p.strip('/'))}(/|$)", path) for p in EXCLUDED_URL_PATTERNS):
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
                        console.print(f"[yellow]Invalid URL: {escape(full_url)}[/yellow]")
                    continue

                parsed = urlparse(full_url)

                # Skip fragment-only URLs (same page anchors)
                if parsed.netloc == base_parsed.netloc and not parsed.path and parsed.fragment:
                    continue

                # Apply crawl type filtering
                if (
                    crawl_type == CrawlType.SINGLE_LEVEL or crawl_type == CrawlType.DOMAIN
                ) and parsed.netloc == base_parsed.netloc:
                    normalized_url = normalize_url(full_url)

                    # Skip URLs that match common exclusion patterns
                    if should_exclude_url(normalized_url):
                        continue

                    # Check robots.txt
                    if respect_robots:
                        if not check_robots_txt(normalized_url):
                            if console:
                                console.print(f"[yellow]Skipping disallowed URL: {escape(normalized_url)}[/yellow]")
                            continue

                    links.add(normalized_url)
                # PAGINATED crawl type implementation would go here
            except Exception as e:
                if console:
                    console.print(f"[red]Error processing link: {escape(str(e))}[/red]")
                continue

        return list(links)
    except Exception as e:
        if console:
            console.print(f"[red]Error extracting links: {escape(str(e))}[/red]")
        return []
