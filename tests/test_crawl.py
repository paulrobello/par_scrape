import sqlite3
from pathlib import Path
from unittest import mock

import pytest
from rich.console import Console

from par_scrape import crawl
from par_scrape.crawl import (
    CrawlType,
    PageStatus,
    clean_url_of_ticket_id,
    is_valid_url,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.sqlite"

@pytest.fixture
def console()->Console:
    return Console(record=True)

@pytest.fixture
def temp_path(tmp_path):
    return tmp_path

@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test.sqlite"
    return db_file



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
        pytest.param("http://example.com/page?ticket=678&param=val", "678", "http://example.com/page?param=val", id = "ticket_in_middle"),
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
        pytest.param("<a href='/page1/Ticket123'>link</a>", "http://example.com", CrawlType.SINGLE_LEVEL, "Ticket123", False, ["http://example.com/page1"], id="full_site_with_ticket_id"),
        pytest.param('<a href="#top">top</a><a href="mailto:test@example.com">email</a>',"http://example.com",CrawlType.SINGLE_LEVEL,"",False,[],id="anchors_and_mailto")
    ])
    def test_extract_links(self, html, base_url, crawl_type, ticket_id, respect_robots, expected_urls, mocker, console):
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

    @pytest.mark.parametrize("url, expected_status", [
        pytest.param("http://example.com", False, id="successful_page"),
        pytest.param("http://example.com/image.jpg", True, id="non_html_page"),
        pytest.param("http://example.com/styles.css", True, id="stylesheet"),
        pytest.param("http://example.com/page?ticket=123", False, id="url_with_ticket_id")
    ])
    def test_should_exclude_url(self, url, expected_status):
        assert crawl.should_exclude_url(url) == expected_status

    @pytest.mark.parametrize("ticket_id, url, expected", [
        pytest.param("Ticket123", "http://example.com", ["Ticket123", "example.com"], id="basic_case"),
        pytest.param("", "http://example.com", ["example.com"], id="no_ticket_id"),
        pytest.param("Ticket123", "http://example.com/page", ["Ticket123", "example.com", "page"], id="ticket and page"),
    ])
    def test_get_url_output_folder(self, tmp_path, ticket_id, url, expected):
        result = crawl.get_url_output_folder(tmp_path, ticket_id, url)
        expectedResult = tmp_path
        for part in expected:
            expectedResult = expectedResult / part
        assert result == expectedResult

    @pytest.mark.parametrize("domain, delay", [
        pytest.param("example.com", 5, id="normal_seconds"),
        pytest.param("example.com", 0, id="zero_delay")
    ])
    def test_set_crawl_delay(self, test_db, domain, delay):
        with mock.patch.object(crawl, "DB_PATH", test_db):
            crawl.init_db()
            crawl.set_crawl_delay(domain, delay)

            with sqlite3.connect(test_db) as conn:
                row = conn.execute("SELECT crawl_delay FROM domain_rate_limit WHERE domain = ?", (domain,)).fetchone()
                assert row is not None
                assert row[0] == delay

class TestQueueFunctions:
    @pytest.mark.parametrize("ticket_id, urls, expected_size", [
        pytest.param("TestTicket", ["http://example.com/page1", "http://example.com/page2"], 2, id="two_urls"),
        pytest.param("", [], 0, id="no_urls"),
        pytest.param("Ticket1", ["http://example.com"] , 1, id="single_url")
    ])
    def test_get_queue_size(self, test_db, ticket_id, urls, expected_size):
        with mock.patch.object(crawl, "DB_PATH", test_db):
            crawl.init_db()
            crawl.add_to_queue(ticket_id, urls)

            size = crawl.get_queue_size(ticket_id)
            assert size == expected_size

    @pytest.mark.parametrize("ticket_id, queue, completed, expected_result", [
        pytest.param("Ticket1", ["http://example.com/page1", "http://example.com/page2"], "", {PageStatus.QUEUED.value: 2, PageStatus.ACTIVE.value: 0, PageStatus.COMPLETED.value: 0, PageStatus.ERROR.value: 0}, id="none_completed"),
        pytest.param("Ticket2", ["http://example.com/page1", "http://example.com/page2"], ["http://example.com/page2"], {PageStatus.QUEUED.value: 1, PageStatus.ACTIVE.value: 0, PageStatus.COMPLETED.value: 1, PageStatus.ERROR.value: 0}, id="completed"),
        pytest.param("Ticket3", "", "", {PageStatus.QUEUED.value: 0, PageStatus.ACTIVE.value: 0, PageStatus.COMPLETED.value: 0, PageStatus.ERROR.value: 0}, id="empty")
    ])
    def test_get_queue_stats(self, test_db, ticket_id, queue, completed, expected_result):
        with mock.patch.object(crawl, "DB_PATH", test_db):
            crawl.init_db()
            crawl.add_to_queue(ticket_id, queue)
            with sqlite3.connect(test_db) as conn:
                for url in completed:
                    conn.execute("UPDATE scrape SET status = ? WHERE ticket_id = ? AND url = ?", (PageStatus.COMPLETED.value, ticket_id, url))
                conn.commit()
            stats = crawl.get_queue_stats(ticket_id)
            assert stats == expected_result

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

class TestMarkFunctions:
    @pytest.mark.parametrize("raw_file_path, file_paths, ticket_id, url",[
        pytest.param(Path("/tmp/raw.html"), {crawl.OutputFormat.MARKDOWN: Path("/tmp/file.md")}, "Ticket1", "http://example.com/page1", id="basic_case"),
        pytest.param(Path("/tmp/raw.html"), {crawl.OutputFormat.MARKDOWN: Path("/tmp/file.md")}, "", "http://example.com/page2", id="no_ticket_id"),
    ])
    def test_mark_complete(self, test_db, raw_file_path, file_paths, ticket_id, url):
        with mock.patch.object(crawl, "DB_PATH", test_db):
            crawl.init_db()
            crawl.add_to_queue(ticket_id, [url])

            crawl.mark_complete(ticket_id, url, raw_file_path=raw_file_path, file_paths=file_paths)

            with sqlite3.connect(test_db) as conn:
                row = conn.execute("SELECT status FROM scrape WHERE ticket_id = ? AND url = ?", (ticket_id, url)).fetchone()
                assert row is not None
                assert row[0] == PageStatus.COMPLETED.value

    @pytest.mark.parametrize("ticket_id, url, error_msg, error_type",[
        pytest.param("Ticket1", "http://example.com/page1", "Page Not Found", crawl.ErrorType.OTHER, id="basic_case"),
        pytest.param("", "http://example.com/page2", "Timeout Error", crawl.ErrorType.OTHER, id="no_ticket_id"),
    ])
    def test_mark_error(self, test_db, ticket_id, url, error_msg, error_type):
        with mock.patch.object(crawl, "DB_PATH", test_db):
            crawl.init_db()
            crawl.add_to_queue(ticket_id, [url])

            crawl.mark_error(ticket_id, url, error_msg=error_msg, error_type=error_type)

            with sqlite3.connect(test_db) as conn:
                row = conn.execute("SELECT status, error_msg, error_type FROM scrape WHERE ticket_id = ? AND url = ?", (ticket_id, url)).fetchone()
                assert row is not None
                assert row[0] == PageStatus.ERROR.value
                assert row[1] == error_msg
                assert row[2] == error_type

    def test_mark_complete_missing_url(self, test_db, tmp_path):
        with mock.patch.object(crawl, "DB_PATH", test_db):
            crawl.init_db()
            crawl.mark_complete("TicketX", "http://nonexistent.com", raw_file_path=tmp_path / "raw.html", file_paths={})
            with sqlite3.connect(test_db) as conn:
                row = conn.execute("SELECT status FROM scrape WHERE ticket_id = ? AND url = ?", ("TicketX", "http://nonexistent.com")).fetchone()
                assert row is None

    def test_mark_error_missing_url(self, test_db, tmp_path):
        with mock.patch.object(crawl, "DB_PATH", test_db):
            crawl.init_db()
            crawl.mark_error("TicketX", "http://nonexistent.com", error_msg="Error", error_type=crawl.ErrorType.OTHER)
            with sqlite3.connect(test_db) as conn:
                row = conn.execute("SELECT status FROM scrape WHERE ticket_id = ? AND url = ?", ("TicketX", "http://nonexistent.com")).fetchone()
                assert row is None





def test_init_db(tmp_path):
    test_db = tmp_path / "test.sqlite"
    with mock.patch.object(crawl, "DB_PATH", test_db):
        crawl.init_db()
        assert test_db.exists()

        with sqlite3.connect(test_db) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            assert "scrape" in tables
            assert "domain_rate_limit" in tables
            assert "db_version" in tables

            cursor = conn.execute("PRAGMA index_list('scrape')")
            indexes = [row[1] for row in cursor.fetchall()]
            assert "idx_status" in indexes
            assert "idx_domain" in indexes
