import pytest
from par_scrape import utils
from par_scrape.exceptions import CrawlConfigError


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com", "https://example.com"),
        ("https://example.com/", "https://example.com"),
        ("https://example.com/test/", "https://example.com/test"),
    ]
)
def test_normalize_url_valid(url, expected):
    assert utils.normalize_url(url) == expected


@pytest.mark.parametrize("url", ["", "notaurl", "http://"])
def test_normalize_url_invalid(url):
    with pytest.raises(CrawlConfigError):
        utils.normalize_url(url)


@pytest.mark.parametrize(
    "url,expected_domain",
    [
        ("https://example.com/path", "example.com"),
        ("http://sub.domain.org/page", "sub.domain.org"),
    ]
)
def test_extract_domain(url, expected_domain):
    assert utils.extract_domain(url) == expected_domain


@pytest.mark.parametrize("items,chunk_size,expected", [
    ([1, 2, 3, 4], 2, [[1, 2], [3, 4]]),
    ([1, 2, 3], 1, [[1], [2], [3]]),
    ([], 3, []),
])
def test_chunk_list(items, chunk_size, expected):
    assert utils.chunk_list(items, chunk_size) == expected


def test_chunk_list_invalid_size():
    with pytest.raises(ValueError):
        utils.chunk_list([1, 2, 3], 0)


@pytest.mark.parametrize("a,b,expected", [
    (4, 2, 2.0),
    (1, 0, 0.0),
])
def test_safe_divide(a, b, expected):
    assert utils.safe_divide(a, b) == expected


def test_merge_dicts():
    a = {"a": 1, "b": 2}
    b = {"b": 3, "c": 4}
    result = utils.merge_dicts(a, b)
    assert result == {"a": 1, "b": 3, "c": 4}
