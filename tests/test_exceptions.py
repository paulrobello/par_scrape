"""Tests for the typed-exception hierarchy and ``classify_error`` router (ARC-004)."""

import urllib.error

import pytest

from par_scrape.enums import ErrorType
from par_scrape.exceptions import (
    InvalidURLError,
    RobotError,
    ScrapeError,
    classify_error,
)

# ---------- isinstance routing (preferred path) ----------


@pytest.mark.parametrize(
    "exc, expected",
    [
        (RobotError("disallowed by robots.txt"), ErrorType.ROBOTS_DISALLOWED),
        (InvalidURLError("bad scheme"), ErrorType.INVALID_URL),
        (TimeoutError("operation timed out"), ErrorType.TIMEOUT),
        (ConnectionError("connection refused"), ErrorType.NETWORK),
        (urllib.error.URLError("no host"), ErrorType.NETWORK),
    ],
)
def test_classify_error_isinstance_routing(exc, expected):
    """Typed par_scrape / stdlib exceptions route by isinstance, not message."""
    assert classify_error(exc) is expected


# ---------- substring fallback (third-party SDKs raise generic exceptions) ----------


@pytest.mark.parametrize(
    "exc, expected",
    [
        # message-keyword fallback
        (RuntimeError("Connection timed out"), ErrorType.TIMEOUT),
        (RuntimeError("network unreachable"), ErrorType.NETWORK),
        (Exception("disallowed by robots.txt"), ErrorType.ROBOTS_DISALLOWED),
        (ValueError("could not parse html"), ErrorType.PARSING),
        (ValueError("invalid url scheme"), ErrorType.INVALID_URL),
        # the catch-all
        (ValueError("whatever"), ErrorType.OTHER),
    ],
)
def test_classify_error_substring_fallback(exc, expected):
    """Generic exceptions route via the message-keyword fallback."""
    assert classify_error(exc) is expected


def test_classify_error_isinstance_takes_precedence_over_message():
    """A RobotError whose message contains no robots keyword still routes correctly."""
    assert classify_error(RobotError("something unrelated")) is ErrorType.ROBOTS_DISALLOWED


def test_scrape_error_is_subclass_of_base():
    """ScrapeError participates in the par_scrape hierarchy (used by ARC-001)."""
    assert issubclass(ScrapeError, Exception)
    with pytest.raises(ScrapeError):
        raise ScrapeError("boom")
