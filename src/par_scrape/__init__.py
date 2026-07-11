"""PAR Scrape - A versatile web scraping tool."""

from __future__ import annotations

__author__ = "Paul Robello"
__copyright__ = "Copyright 2025, Paul Robello"
__credits__ = ["Paul Robello"]
__maintainer__ = "Paul Robello"
__email__ = "probello@gmail.com"
__version__ = "0.10.0"
__licence__ = "MIT"
__application_title__ = "PAR Scrape"
__application_binary__ = "par_scrape"

# Public library API (ENH-005, provisional). Imported after the module metadata
# above is defined: par_scrape.api -> par_scrape.runner -> `from par_scrape import
# __application_title__, __version__`, so the metadata must exist first to avoid
# a circular import.
from par_scrape.api import PageResult, ScrapeResult, scrape

__all__: list[str] = [
    "__author__",
    "__copyright__",
    "__credits__",
    "__maintainer__",
    "__email__",
    "__version__",
    "__licence__",
    "__application_title__",
    "__application_binary__",
    # Public library API (ENH-005, provisional)
    "PageResult",
    "ScrapeResult",
    "scrape",
]
