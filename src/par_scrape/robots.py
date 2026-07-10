"""robots.txt fetching and fetch policy."""

import threading
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse

# Default user agent for robots.txt
DEFAULT_USER_AGENT = "par-scrape/1.0 (+https://github.com/paulrobello/par_scrape)"

# Global dictionary to store robots.txt parsers by domain
ROBOTS_PARSERS: dict[str, urllib.robotparser.RobotFileParser] = {}
# Lock for thread-safe access to ROBOTS_PARSERS
ROBOTS_PARSERS_LOCK = threading.Lock()


def check_robots_txt(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """
    Check if a URL is allowed by the site's robots.txt.

    Fail-open policy: if robots.txt cannot be fetched (timeout, connection error,
    or HTTP error such as 5xx/429), the URL is treated as ALLOWED and the crawler
    proceeds as if no restrictions exist. par_scrape is a user-requested crawler, so
    an unreachable robots.txt must not abort the crawl; only a successfully fetched
    and parsed robots.txt can disallow a URL. This is a deliberate product decision,
    not a bug; switching to fail-closed would require an explicit opt-in.

    Args:
        url: The URL to check
        user_agent: User agent to use for robots.txt checking

    Returns:
        bool: True if the URL is allowed, False if disallowed
    """
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        # Snapshot any cached parser under the lock; the network fetch happens
        # outside the lock so a slow robots.txt never serializes other workers.
        with ROBOTS_PARSERS_LOCK:
            rp = ROBOTS_PARSERS.get(domain)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{parsed_url.scheme}://{domain}/robots.txt"
            rp.set_url(robots_url)
            try:
                with urllib.request.urlopen(robots_url, timeout=10) as response:
                    rp.parse(line.decode("utf-8", errors="replace") for line in response)
            except Exception:
                # Fail-open: an unreachable robots.txt must not block the domain.
                # allow_all must be set or a never-parsed parser returns False
                # from can_fetch (last_checked == 0), silently denying every
                # subsequent URL on the domain. Direct assignment fails pyright
                # because typeshed doesn't model allow_all as writable here.
                setattr(rp, "allow_all", True)  # noqa: B010 - typeshed omits allow_all; see comment
            # Double-checked insert: a concurrent worker may have populated the
            # same domain; either way we adopt the cached instance.
            with ROBOTS_PARSERS_LOCK:
                ROBOTS_PARSERS.setdefault(domain, rp)
                rp = ROBOTS_PARSERS[domain]
        return rp.can_fetch(user_agent, url)
    except Exception:
        # On any failure, default to allowing the URL
        return True
