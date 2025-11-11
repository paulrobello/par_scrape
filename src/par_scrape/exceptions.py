# par_scrape/exceptions.py

class ParScrapeError(Exception):
    """Base exception for all par_scrape errors."""
    pass


class CrawlConfigError(ParScrapeError):
    """Raised when crawl or scrape configuration is invalid."""
    pass


class ProviderConfigError(ParScrapeError):
    """Raised when AI provider or model configuration is invalid."""
    pass
