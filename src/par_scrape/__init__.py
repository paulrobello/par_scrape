"""PAR Scrape - A versatile web scraping tool."""

from __future__ import annotations

import os

__author__ = "Paul Robello"
__copyright__ = "Copyright 2025, Paul Robello"
__credits__ = ["Paul Robello"]
__maintainer__ = "Paul Robello"
__email__ = "probello@gmail.com"
__version__ = "0.8.3"
__licence__ = "MIT"
__application_title__ = "PAR Scrape"
__application_binary__ = "par_scrape"

os.environ["USER_AGENT"] = f"{__application_title__} {__version__}"

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
]
