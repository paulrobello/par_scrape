import pytest
from pathlib import Path
from par_scrape import crawl
from par_scrape.crawl import(
    is_valid_url,
    clean_url_of_ticket_id,
    check_robots_txt,
    add_to_queue,
    get_next_urls,
    PageStatus,
    CrawlType,
    ROBOTS_PARSERS,
)
@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.sqlite"

@pytest.fixture
def console():
    return Console(record=True)
        
    

class TestCrawlFunctions:

    @pytest.mark.parametrize("url, expected", [
        pytest.param("http://example.com", True, id="valid_http"),
        pytest.param("https://example.com/page", True, id="valid_https"),
        pytest.param("ftp://example.com", False, id="invalid_scheme"),
        pytest.param("non-url", False, id="not_a_url")
    ])
    def test_is_valid_url(self, url, expected):
        assert is_valid_url(url) == expected

    @pytest.mark.parametrize("url, ticket_id, expected", [ 
        pytest.param("http://example.com/page?ticket=12345", "12345", "http://example.com/page", id="with_ticket"),
        pytest.param("http://example.com/page", "", "http://example.com/page", id="without_ticket"),
        pytest.param("http://example.com/page?param=value&ticket=67890", "67890", "http://example.com/page?param=value", id="with_other_params"),
        pytest.param("not-url", None, "not-url", id="invalid_url")
    ])
    def test_clean_url_of_ticket_id(self, url, ticket_id, expected):
        assert clean_url_of_ticket_id(url, ticket_id) == expected

    @pytest.mark.parametrize("url, parser_setup, expected",[
        pytest.param("http://example.com", {"can_fetch": True}, True, id="allowed_by_robots"),
        pytest.param("http://example.com/private", {"can_fetch": False}, False, id="disallowed_by_robots")
    ])
    def test_check_robots_txt(self, url, parser_setup, expected, mocker):
        mocker.patch.dict(crawl.ROBOTS_PARSERS, clear=True)
        
        if parser_setup:
            domain = crawl.urlparse(url).netloc
            mock_rp = mocker.Mock()
            mock_rp.can_fetch.return_value = parser_setup["can_fetch"]
            crawl.ROBOTS_PARSERS[domain] = mock_rp

        result = crawl.check_robots_txt(url)
        assert result == expected

    @pytest.mark.parametrize("urls, ticket_id, expected_count", [
        pytest.param(["http://example.com/page1"], "Ticket1", 1, id="one_url"),
        pytest.param(["http://example.com/page1", "http://example.com/page2?ticket=123"], "Ticket2", 2, id="add_multiple_urls"),
        pytest.param(["http://example.com/page1"], "", 1, id="no_ticket_id"),
        pytest.param([], "Ticket3", 0, id="empty_url_list"),
        pytest.param(["invalid-url"], "Ticket4", 0, id="invalid_url")
    ])
    def test_add_to_queue(self, db_path, urls, ticket_id, expected_count, monkeypatch):
        assert db_path.name == "test.sqlite"
        monkeypatch.setattr(crawl, "DB_PATH", db_path)

        crawl.init_db()

        crawl.add_to_queue(ticket_id, urls)

        from sqlite3 import connect
        with connect(db_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM scrape WHERE ticket_id = ?", (ticket_id,)).fetchone()
            assert row[0] == expected_count

    @pytest.mark.parametrize("url_queue, expected_next", [
        pytest.param(["http://example.com/page1"], ["http://example.com/page1"], id="single_url"),
        pytest.param(["http://example.com/page1", "http://example.com/page2"], ["http://example.com/page1"], id="multiple_urls"),
        pytest.param([], [], id="empty_queue")
    ])
    def test_get_next_urls(self, db_path, url_queue, expected_next, monkeypatch):
        assert db_path.name == "test.sqlite"
        monkeypatch.setattr(crawl, "DB_PATH", db_path)

        crawl.init_db()

        ticket_id = "TestTicket"
        crawl.add_to_queue(ticket_id, url_queue)

        next_urls = crawl.get_next_urls(ticket_id, crawl_batch_size=1)
        assert next_urls == expected_next

    @pytest.mark.parametrize("html, base_url, crawl_type, ticket_id, respect_robots, expected_urls",[
        pytest.param("<a href='/page1'>link</a>", "http://example.com", CrawlType.SINGLE_PAGE, "", False, "", id="single_page_no_robots"),
        pytest.param("<a href='/page1'>link</a>", "http://example.com", CrawlType.SINGLE_PAGE, "", False, [], id="single_page_with_robots"),
        pytest.param("<a href='/page1'>link</a><a href='/page2'>link2</a>", "http://example.com", CrawlType.SINGLE_LEVEL, "Ticket1", False, ["http://example.com/page1", "http://example.com/page2"], id="full_site_no_robots"),
        pytest.param("<a href='/page1/Ticket123'>link</a>", "http://example.com", CrawlType.SINGLE_LEVEL, "Ticket123", False, ["http://example.com/page1"], id="full_site_with_ticket_id")
    ])
    def test_extract_links(self, html, base_url, crawl_type, ticket_id, respect_robots, expected_urls, mocker):
        mocker.patch("par_scrape.crawl.check_robots_txt", return_value=True)

        result = crawl.extract_links(
            base_url = base_url,
            html = html,
            crawl_type = crawl_type,
            ticket_id = ticket_id,
            respect_robots = respect_robots,
            console = console
        )
        assert set(result) == set(expected_urls)