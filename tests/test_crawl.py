import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

import pytest
from rich.console import Console

from par_scrape import crawl, queue_db, robots
from par_scrape.crawl import (
    CrawlType,
    PageStatus,
    is_valid_url,
)


@pytest.fixture
def console() -> Console:
    return Console(record=True)


class TestCrawlFunctions:
    @pytest.mark.parametrize(
        "url, expected",
        [
            pytest.param("http://example.com", True, id="valid_http"),
            pytest.param("https://example.com/page", True, id="valid_https"),
            pytest.param("ftp://example.com", False, id="invalid_scheme"),
            pytest.param("non-url", False, id="not_a_url"),
        ],
    )
    def test_is_valid_url(self, url, expected):
        assert is_valid_url(url) == expected

    @pytest.mark.parametrize(
        "url, parser_setup, expected",
        [
            pytest.param("http://example.com", {"can_fetch": True}, True, id="allowed_by_robots"),
            pytest.param("http://example.com/private", {"can_fetch": False}, False, id="disallowed_by_robots"),
        ],
    )
    def test_check_robots_txt(self, url, parser_setup, expected, mocker):
        mocker.patch.dict(robots.ROBOTS_PARSERS, clear=True)

        if parser_setup:
            domain = urlparse(url).netloc
            mock_rp = mocker.Mock()
            mock_rp.can_fetch.return_value = parser_setup["can_fetch"]
            robots.ROBOTS_PARSERS[domain] = mock_rp

        result = crawl.check_robots_txt(url)
        assert result == expected

    def test_check_robots_txt_fail_open_on_fetch_error(self, mocker):
        """QA-002/QA-006: an unreachable robots.txt must fail open, and the
        allow-all result must be cached so subsequent calls on the domain also
        return True (regression: a never-parsed parser previously returned
        False from can_fetch and silently blocked the whole domain)."""
        mocker.patch.dict(robots.ROBOTS_PARSERS, clear=True)
        mocker.patch("urllib.request.urlopen", side_effect=OSError("unreachable"))

        first = crawl.check_robots_txt("https://x.test/a")
        second = crawl.check_robots_txt("https://x.test/b")

        assert first is True
        assert second is True

    @pytest.mark.parametrize(
        "url_queue, expected_next",
        [
            pytest.param(["http://example.com/page1"], ["http://example.com/page1"], id="single_url"),
            pytest.param(
                ["http://example.com/page1", "http://example.com/page2"],
                ["http://example.com/page1"],
                id="multiple_urls",
            ),
            pytest.param([], [], id="empty_queue"),
        ],
    )
    def test_get_next_urls(self, db_path, url_queue, expected_next):
        assert db_path.name == "test.sqlite"

        ticket_id = "TestTicket"
        crawl.add_to_queue(ticket_id, url_queue, db_path=db_path)

        next_urls = crawl.get_next_urls(ticket_id, crawl_batch_size=1, db_path=db_path)
        assert next_urls == expected_next

    @pytest.mark.parametrize(
        "html, base_url, crawl_type, ticket_id, respect_robots, expected_urls",
        [
            pytest.param(
                "<a href='/page1'>link</a>",
                "http://example.com",
                CrawlType.SINGLE_PAGE,
                "",
                False,
                [],
                id="single_page_no_robots",
            ),
            pytest.param(
                "<a href='/page1'>link</a>",
                "http://example.com",
                CrawlType.SINGLE_PAGE,
                "",
                False,
                [],
                id="single_page_with_robots",
            ),
            pytest.param(
                "<a href='/page1'>link</a><a href='/page2'>link2</a>",
                "http://example.com",
                CrawlType.SINGLE_LEVEL,
                "Ticket1",
                False,
                ["http://example.com/page1", "http://example.com/page2"],
                id="full_site_no_robots",
            ),
            pytest.param(
                "<a href='/page1/Ticket123'>link</a>",
                "http://example.com",
                CrawlType.SINGLE_LEVEL,
                "Ticket123",
                False,
                ["http://example.com/page1/Ticket123"],
                id="full_site_ticket_id_preserved",
            ),
            pytest.param(
                '<a href="#top">top</a><a href="mailto:test@example.com">email</a>',
                "http://example.com",
                CrawlType.SINGLE_LEVEL,
                "",
                False,
                [],
                id="anchors_and_mailto",
            ),
        ],
    )
    def test_extract_links(self, html, base_url, crawl_type, ticket_id, respect_robots, expected_urls, mocker, console):
        mocker.patch("par_scrape.links.check_robots_txt", return_value=True)

        result = crawl.extract_links(
            base_url=base_url,
            html=html,
            crawl_type=crawl_type,
            ticket_id=ticket_id,
            respect_robots=respect_robots,
            console=console,
        )
        assert set(result) == set(expected_urls)

    @pytest.mark.parametrize(
        "url, expected_status",
        [
            pytest.param("http://example.com", False, id="successful_page"),
            pytest.param("http://example.com/image.jpg", True, id="non_html_page"),
            pytest.param("http://example.com/styles.css", True, id="stylesheet"),
            pytest.param("http://example.com/page?ticket=123", False, id="url_with_ticket_id"),
        ],
    )
    def test_should_exclude_url(self, url, expected_status):
        assert crawl.should_exclude_url(url) == expected_status

    @pytest.mark.parametrize(
        "url, expected_status",
        [
            pytest.param("http://example.com/feedback", False, id="feedback_not_feed"),
            pytest.param("http://example.com/feed", True, id="feed_excluded"),
            pytest.param("http://example.com/blog/feed", True, id="nested_feed_excluded"),
            pytest.param("http://example.com/feed/x", True, id="feed_segment_then_child_excluded"),
        ],
    )
    def test_should_exclude_url_segment_anchoring(self, url, expected_status):
        """ARC-019: patterns anchor on path segments (/feed must not match /feedback)."""
        assert crawl.should_exclude_url(url) == expected_status

    @pytest.mark.parametrize(
        "ticket_id, url, expected",
        [
            pytest.param("Ticket123", "http://example.com", ["Ticket123", "example.com"], id="basic_case"),
            pytest.param("", "http://example.com", ["example.com"], id="no_ticket_id"),
            pytest.param(
                "Ticket123", "http://example.com/page", ["Ticket123", "example.com", "page"], id="ticket and page"
            ),
            pytest.param(
                "docs",
                "https://example.com/docs/intro",
                ["docs", "example.com", "docs__intro"],
                id="run_name_in_path_preserved",
            ),
        ],
    )
    def test_get_url_output_folder(self, tmp_path, ticket_id, url, expected):
        result = crawl.get_url_output_folder(tmp_path, ticket_id, url)
        expected_path = tmp_path
        for part in expected:
            expected_path = expected_path / part
        assert result == expected_path

    def test_get_url_output_folder_rejects_traversal_netloc(self, tmp_path):
        """SEC-006: a netloc of '..' must not escape the run folder."""
        with pytest.raises(ValueError, match="Invalid URL host"):
            crawl.get_url_output_folder(tmp_path, "run", "http://../x")

    @pytest.mark.parametrize(
        "domain, delay",
        [pytest.param("example.com", 5, id="normal_seconds"), pytest.param("example.com", 0, id="zero_delay")],
    )
    def test_set_crawl_delay(self, db_path, domain, delay):
        crawl.set_crawl_delay(domain, delay, db_path=db_path)

        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute("SELECT crawl_delay FROM domain_rate_limit WHERE domain = ?", (domain,)).fetchone()
            assert row is not None
            assert row[0] == delay


class TestQueueFunctions:
    @pytest.mark.parametrize(
        "ticket_id, queue, completed, expected_result",
        [
            pytest.param(
                "Ticket1",
                ["http://example.com/page1", "http://example.com/page2"],
                "",
                {
                    PageStatus.QUEUED.value: 2,
                    PageStatus.ACTIVE.value: 0,
                    PageStatus.COMPLETED.value: 0,
                    PageStatus.ERROR.value: 0,
                },
                id="none_completed",
            ),
            pytest.param(
                "Ticket2",
                ["http://example.com/page1", "http://example.com/page2"],
                ["http://example.com/page2"],
                {
                    PageStatus.QUEUED.value: 1,
                    PageStatus.ACTIVE.value: 0,
                    PageStatus.COMPLETED.value: 1,
                    PageStatus.ERROR.value: 0,
                },
                id="completed",
            ),
            pytest.param(
                "Ticket3",
                "",
                "",
                {
                    PageStatus.QUEUED.value: 0,
                    PageStatus.ACTIVE.value: 0,
                    PageStatus.COMPLETED.value: 0,
                    PageStatus.ERROR.value: 0,
                },
                id="empty",
            ),
        ],
    )
    def test_get_queue_stats(self, db_path, ticket_id, queue, completed, expected_result):
        crawl.add_to_queue(ticket_id, queue, db_path=db_path)
        with closing(sqlite3.connect(db_path)) as conn, conn:
            for url in completed:
                conn.execute(
                    "UPDATE scrape SET status = ? WHERE ticket_id = ? AND url = ?",
                    (PageStatus.COMPLETED.value, ticket_id, url),
                )
            conn.commit()
        stats = crawl.get_queue_stats(ticket_id, db_path=db_path)
        assert stats == expected_result

    @pytest.mark.parametrize(
        "urls, ticket_id, expected_count",
        [
            pytest.param(["http://example.com/page1"], "Ticket1", 1, id="one_url"),
            pytest.param(
                ["http://example.com/page1", "http://example.com/page2?ticket=123"],
                "Ticket2",
                2,
                id="add_multiple_urls",
            ),
            pytest.param(["http://example.com/page1"], "", 1, id="no_ticket_id"),
            pytest.param([], "Ticket3", 0, id="empty_url_list"),
            pytest.param(["invalid-url"], "Ticket4", 0, id="invalid_url"),
        ],
    )
    def test_add_to_queue(self, db_path, urls, ticket_id, expected_count):
        assert db_path.name == "test.sqlite"

        crawl.add_to_queue(ticket_id, urls, db_path=db_path)

        with closing(sqlite3.connect(db_path)) as connection, connection:
            row = connection.execute("SELECT COUNT(*) FROM scrape WHERE ticket_id = ?", (ticket_id,)).fetchone()
            assert row[0] == expected_count

    def test_add_to_queue_preserves_url_containing_run_name(self, db_path):
        """ARC-003: a URL containing the run name is queued verbatim (not rewritten).

        Previously ``--run-name docs`` with URL ``/docs/intro`` was fetched as
        ``/intro``; URLs are now identifiers and must survive add_to_queue intact.
        """
        run_name = "docs"
        url = "https://example.com/docs/intro"
        crawl.add_to_queue(run_name, [url], db_path=db_path)

        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute("SELECT url FROM scrape WHERE ticket_id = ?", (run_name,)).fetchone()
            assert row is not None
            # The run-name path segment "docs" must survive (old code stripped it).
            assert "example.com/docs/intro" in row[0]
            assert row[0] != "https://example.com/intro"


class TestMarkFunctions:
    @pytest.mark.parametrize(
        "raw_file_path, file_paths, ticket_id, url",
        [
            pytest.param(
                Path("/tmp/raw.html"),
                {crawl.OutputFormat.MARKDOWN: Path("/tmp/file.md")},
                "Ticket1",
                "http://example.com/page1",
                id="basic_case",
            ),
            pytest.param(
                Path("/tmp/raw.html"),
                {crawl.OutputFormat.MARKDOWN: Path("/tmp/file.md")},
                "",
                "http://example.com/page2",
                id="no_ticket_id",
            ),
        ],
    )
    def test_mark_complete(self, db_path, raw_file_path, file_paths, ticket_id, url):
        crawl.add_to_queue(ticket_id, [url], db_path=db_path)

        crawl.mark_complete(ticket_id, url, raw_file_path=raw_file_path, file_paths=file_paths, db_path=db_path)

        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute("SELECT status FROM scrape WHERE ticket_id = ? AND url = ?", (ticket_id, url)).fetchone()
            assert row is not None
            assert row[0] == PageStatus.COMPLETED.value

    @pytest.mark.parametrize(
        "ticket_id, url, error_msg, error_type",
        [
            pytest.param(
                "Ticket1", "http://example.com/page1", "Page Not Found", crawl.ErrorType.OTHER, id="basic_case"
            ),
            pytest.param("", "http://example.com/page2", "Timeout Error", crawl.ErrorType.OTHER, id="no_ticket_id"),
        ],
    )
    def test_mark_error(self, db_path, ticket_id, url, error_msg, error_type):
        crawl.add_to_queue(ticket_id, [url], db_path=db_path)

        crawl.mark_error(ticket_id, url, error_msg=error_msg, error_type=error_type, db_path=db_path)

        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT status, error_msg, error_type FROM scrape WHERE ticket_id = ? AND url = ?", (ticket_id, url)
            ).fetchone()
            assert row is not None
            assert row[0] == PageStatus.ERROR.value
            assert row[1] == error_msg
            assert row[2] == error_type

    def test_mark_complete_missing_url(self, db_path, tmp_path):
        crawl.mark_complete(
            "TicketX", "http://nonexistent.com", raw_file_path=tmp_path / "raw.html", file_paths={}, db_path=db_path
        )
        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT status FROM scrape WHERE ticket_id = ? AND url = ?", ("TicketX", "http://nonexistent.com")
            ).fetchone()
            assert row is None

    def test_mark_error_missing_url(self, db_path, tmp_path):
        crawl.mark_error(
            "TicketX", "http://nonexistent.com", error_msg="Error", error_type=crawl.ErrorType.OTHER, db_path=db_path
        )
        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT status FROM scrape WHERE ticket_id = ? AND url = ?", ("TicketX", "http://nonexistent.com")
            ).fetchone()
            assert row is None


class TestFilePathsJsonColumn:
    """ARC-010: per-format paths are stored in a single JSON ``file_paths`` column."""

    def test_mark_complete_stores_file_paths_json(self, db_path):
        crawl.add_to_queue("Ticket1", ["http://example.com/page1"], db_path=db_path)

        file_paths = {
            crawl.OutputFormat.MARKDOWN: Path("/tmp/file.md"),
            crawl.OutputFormat.JSON: Path("/tmp/file.json"),
        }
        crawl.mark_complete(
            "Ticket1",
            "http://example.com/page1",
            raw_file_path=Path("/tmp/raw.html"),
            file_paths=file_paths,
            db_path=db_path,
        )

        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT raw_file_path, file_paths FROM scrape WHERE ticket_id = ? AND url = ?",
                ("Ticket1", "http://example.com/page1"),
            ).fetchone()
            assert row is not None
            assert row[0] == "/tmp/raw.html"
            parsed = json.loads(row[1])
            assert parsed == {"md": "/tmp/file.md", "json": "/tmp/file.json"}

    def test_mark_complete_empty_file_paths_is_valid_json_or_null(self, db_path):
        crawl.add_to_queue("Ticket1", ["http://example.com/page1"], db_path=db_path)

        crawl.mark_complete(
            "Ticket1",
            "http://example.com/page1",
            raw_file_path=Path("/tmp/raw.html"),
            file_paths={},
            db_path=db_path,
        )

        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT file_paths FROM scrape WHERE ticket_id = ? AND url = ?",
                ("Ticket1", "http://example.com/page1"),
            ).fetchone()
            assert row is not None
            # An empty mapping still round-trips through json as "{}".
            assert json.loads(row[0]) == {}


def test_init_db(tmp_path):
    test_db = tmp_path / "test.sqlite"
    crawl.init_db(db_path=test_db)
    assert test_db.exists()

    with closing(sqlite3.connect(test_db)) as conn, conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert "scrape" in tables
        assert "domain_rate_limit" in tables
        assert "db_version" in tables

        cursor = conn.execute("PRAGMA index_list('scrape')")
        indexes = [row[1] for row in cursor.fetchall()]
        assert "idx_status" in indexes
        assert "idx_domain" in indexes


class TestQueueHelpers:
    """ARC-005: queue_db helpers move inline SQL out of the presentation layer."""

    def test_get_url_depth_returns_stored_depth(self, db_path):
        crawl.add_to_queue("Ticket1", ["http://example.com/page1"], depth=3, db_path=db_path)

        assert queue_db.get_url_depth("Ticket1", "http://example.com/page1", db_path=db_path) == 3

    def test_get_url_depth_defaults_to_zero_for_missing_url(self, db_path):
        assert queue_db.get_url_depth("Ticket1", "http://example.com/missing", db_path=db_path) == 0

    def test_increase_crawl_delay_doubles_and_caps(self, db_path):
        domain = "example.com"
        # add_to_queue seeds the domain with crawl_delay = 1
        crawl.add_to_queue("Ticket1", ["http://example.com/page1"], db_path=db_path)

        assert queue_db.increase_crawl_delay(domain, db_path=db_path) == 2
        assert queue_db.increase_crawl_delay(domain, db_path=db_path) == 4
        assert queue_db.increase_crawl_delay(domain, db_path=db_path) == 8

        # cap at 30 seconds
        crawl.set_crawl_delay(domain, 20, db_path=db_path)
        assert queue_db.increase_crawl_delay(domain, db_path=db_path) == 30
        assert queue_db.increase_crawl_delay(domain, db_path=db_path) == 30


def test_init_db_renames_incompatible_database_aside(tmp_path):
    """ARC-009: a DB lacking db_version is moved aside, not deleted."""
    test_db = tmp_path / "test.sqlite"
    test_db.write_bytes(b"dummy old database content that is not a real sqlite file")

    crawl.init_db(db_path=test_db)

    # The old file was renamed aside, not deleted.
    backups = list(tmp_path.glob("test.sqlite.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"dummy old database content that is not a real sqlite file"

    # A fresh working database was created in its place.
    assert test_db.exists()
    with closing(sqlite3.connect(test_db)) as conn, conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert "db_version" in tables
        assert "scrape" in tables


def test_init_db_upgrades_old_v1_database_via_rename_aside(tmp_path):
    """ARC-009 + ARC-010: an existing v1 DB is renamed aside (not destroyed and
    not wrongly altered) when the schema version bumps to 2."""
    test_db = tmp_path / "test.sqlite"
    # Build a genuine v1 database with the legacy per-format path columns.
    with closing(sqlite3.connect(test_db)) as conn, conn:
        conn.execute(
            """
            CREATE TABLE scrape (
                ticket_id TEXT, url TEXT, status TEXT, raw_file_path TEXT,
                md_file_path TEXT, json_file_path TEXT, csv_file_path TEXT, excel_file_path TEXT,
                depth INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO scrape (ticket_id, url, status, md_file_path) VALUES ('T1', 'u', 'completed', '/old.md')"
        )
        conn.execute("CREATE TABLE db_version (version INTEGER PRIMARY KEY, created_at INTEGER, description TEXT)")
        conn.execute("INSERT INTO db_version (version, description) VALUES (1, 'legacy v1')")
    assert test_db.exists()

    crawl.init_db(db_path=test_db)

    # The v1 database was moved aside, preserving the user's data.
    backups = list(tmp_path.glob("test.sqlite.bak-v1*"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as conn, conn:
        legacy_cols = [r[1] for r in conn.execute("PRAGMA table_info(scrape)")]
        assert "md_file_path" in legacy_cols  # old schema intact in the backup
        row = conn.execute("SELECT md_file_path FROM scrape WHERE ticket_id = 'T1'").fetchone()
        assert row[0] == "/old.md"

    # A fresh v2 database now exists with the JSON file_paths column.
    assert test_db.exists()
    with closing(sqlite3.connect(test_db)) as conn, conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(scrape)")]
        assert "file_paths" in cols
        assert "md_file_path" not in cols
        v = conn.execute("SELECT version FROM db_version ORDER BY version DESC LIMIT 1").fetchone()[0]
        assert v == queue_db.DB_VERSION


class TestConnectionReuse:
    """ENH-004: per-thread cached connections opened in WAL journal mode."""

    def test_get_connection_enables_wal_mode(self, db_path: Path) -> None:
        queue_db._get_connection(db_path)
        mode = queue_db._get_connection(db_path).execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_get_connection_caches_per_thread(self, db_path: Path) -> None:
        first = queue_db._get_connection(db_path)
        second = queue_db._get_connection(db_path)
        assert first is second

    def test_get_connection_is_thread_local(self, db_path: Path) -> None:
        main_conn = queue_db._get_connection(db_path)
        holder: dict[str, object] = {}

        def worker() -> None:
            holder["conn"] = queue_db._get_connection(db_path)
            queue_db.close_connections()  # release this thread's connection

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert holder["conn"] is not main_conn

    def test_concurrent_writers_do_not_lock(self, db_path: Path) -> None:
        errors: list[str] = []

        def worker(worker_id: int) -> None:
            try:
                for i in range(25):
                    url = f"http://example-{worker_id}-{i}.com/page{i}"
                    queue_db.add_to_queue("ticket", [url], db_path=db_path)
                    queue_db.mark_complete(
                        "ticket",
                        url,
                        raw_file_path=Path("/tmp/raw.md"),
                        file_paths={},
                        db_path=db_path,
                    )
            except Exception as exc:  # noqa: BLE001 - surface any failure type
                errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                queue_db.close_connections()

        threads = [threading.Thread(target=worker, args=(worker_id,)) for worker_id in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        stats = queue_db.get_queue_stats("ticket", db_path=db_path)
        assert stats[PageStatus.COMPLETED.value] == 100


class TestFindCompletedByHash:
    """ENH-002: locate a prior run's completed row by URL + content hash."""

    URL = "https://example.com/page1"

    def _insert_row(
        self, db_path, ticket_id, content_hash, status=PageStatus.COMPLETED.value, file_paths='{"json": "/tmp/a.json"}'
    ):
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute(
                "INSERT INTO scrape (ticket_id, url, status, content_hash, file_paths) VALUES (?, ?, ?, ?, ?)",
                (ticket_id, self.URL, status, content_hash, file_paths),
            )

    def test_finds_prior_completed_row_from_another_run(self, db_path):
        self._insert_row(db_path, "run-a", "hash-abc")
        result = queue_db.find_completed_by_hash(self.URL, "hash-abc", exclude_ticket_id="run-b")
        assert result is not None
        assert result["file_paths"] == '{"json": "/tmp/a.json"}'

    def test_excludes_current_run_self(self, db_path):
        self._insert_row(db_path, "run-a", "hash-abc")
        assert queue_db.find_completed_by_hash(self.URL, "hash-abc", exclude_ticket_id="run-a") is None

    def test_returns_none_when_hash_differs(self, db_path):
        self._insert_row(db_path, "run-a", "hash-abc")
        assert queue_db.find_completed_by_hash(self.URL, "hash-different", exclude_ticket_id="run-b") is None

    def test_returns_none_when_prior_row_errored(self, db_path):
        self._insert_row(db_path, "run-a", "hash-abc", status=PageStatus.ERROR.value)
        assert queue_db.find_completed_by_hash(self.URL, "hash-abc", exclude_ticket_id="run-b") is None

    def test_returns_most_recent_when_multiple_prior_runs_match(self, db_path):
        # Two prior runs with the same url+hash; rowid DESC must pick the last inserted.
        self._insert_row(db_path, "run-a", "hash-abc", file_paths='{"json": "/tmp/old.json"}')
        self._insert_row(db_path, "run-b", "hash-abc", file_paths='{"json": "/tmp/new.json"}')
        result = queue_db.find_completed_by_hash(self.URL, "hash-abc", exclude_ticket_id="run-current")
        assert result is not None
        assert result["file_paths"] == '{"json": "/tmp/new.json"}'


class TestContentHashColumn:
    """ENH-002: mark_complete records the content_hash for incremental reuse."""

    def test_mark_complete_stores_content_hash(self, db_path):
        crawl.add_to_queue("Ticket1", [TestFindCompletedByHash.URL], db_path=db_path)
        crawl.mark_complete(
            "Ticket1",
            TestFindCompletedByHash.URL,
            raw_file_path=Path("/tmp/raw.html"),
            file_paths={crawl.OutputFormat.JSON: Path("/tmp/a.json")},
            content_hash="deadbeef",
            db_path=db_path,
        )
        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT content_hash FROM scrape WHERE ticket_id = ? AND url = ?",
                ("Ticket1", TestFindCompletedByHash.URL),
            ).fetchone()
        assert row is not None
        assert row[0] == "deadbeef"

    def test_mark_complete_content_hash_defaults_to_null(self, db_path):
        url = "https://example.com/page2"
        crawl.add_to_queue("Ticket1", [url], db_path=db_path)
        crawl.mark_complete(
            "Ticket1",
            url,
            raw_file_path=Path("/tmp/raw.html"),
            file_paths={},
            db_path=db_path,
        )
        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT content_hash FROM scrape WHERE ticket_id = ? AND url = ?",
                ("Ticket1", url),
            ).fetchone()
        assert row is not None
        assert row[0] is None


class TestQueueManagement:
    """ENH-006: list_runs / get_run_pages / requeue_errors / delete_run."""

    def test_list_runs_reports_per_status_counts(self, db_path):
        crawl.add_to_queue("runA", ["https://example.com/a1", "https://example.com/a2"], db_path=db_path)
        crawl.mark_error("runA", "https://example.com/a1", "boom", db_path=db_path)
        crawl.add_to_queue("runB", ["https://example.com/b1"], db_path=db_path)
        crawl.mark_complete(
            "runB",
            "https://example.com/b1",
            raw_file_path=Path("/tmp/r.md"),
            file_paths={},
            db_path=db_path,
        )

        runs = dict(crawl.list_runs(db_path=db_path))
        assert "runA" in runs and "runB" in runs
        assert runs["runA"][crawl.PageStatus.ERROR.value] == 1
        assert runs["runA"][crawl.PageStatus.QUEUED.value] == 1
        assert runs["runB"][crawl.PageStatus.COMPLETED.value] == 1

    def test_get_run_pages_returns_rows_by_name(self, db_path):
        crawl.add_to_queue("runA", ["https://example.com/a1"], db_path=db_path)
        crawl.mark_error("runA", "https://example.com/a1", "boom", error_type=crawl.ErrorType.NETWORK, db_path=db_path)

        pages = crawl.get_run_pages("runA", db_path=db_path)
        assert len(pages) == 1
        row = pages[0]
        assert row["url"] == "https://example.com/a1"
        assert row["status"] == "error"
        assert row["error_type"] == "network"

    def test_requeue_errors_resets_status_and_returns_count(self, db_path):
        crawl.add_to_queue("runA", ["https://example.com/a1", "https://example.com/a2"], db_path=db_path)
        crawl.mark_error("runA", "https://example.com/a1", "boom", db_path=db_path)
        crawl.mark_error("runA", "https://example.com/a2", "boom", db_path=db_path)

        requeued = crawl.requeue_errors("runA", db_path=db_path)
        assert requeued == 2
        stats = crawl.get_queue_stats("runA", db_path=db_path)
        assert stats[crawl.PageStatus.ERROR.value] == 0
        assert stats[crawl.PageStatus.QUEUED.value] == 2

    def test_requeue_errors_only_affects_target_run(self, db_path):
        crawl.add_to_queue("runA", ["https://example.com/a1"], db_path=db_path)
        crawl.add_to_queue("runB", ["https://example.com/b1"], db_path=db_path)
        crawl.mark_error("runA", "https://example.com/a1", "boom", db_path=db_path)
        crawl.mark_error("runB", "https://example.com/b1", "boom", db_path=db_path)

        assert crawl.requeue_errors("runA", db_path=db_path) == 1
        assert crawl.get_queue_stats("runB", db_path=db_path)[crawl.PageStatus.ERROR.value] == 1

    def test_delete_run_removes_only_target(self, db_path):
        crawl.add_to_queue("runA", ["https://example.com/a1"], db_path=db_path)
        crawl.add_to_queue("runB", ["https://example.com/b1", "https://example.com/b2"], db_path=db_path)

        removed = crawl.delete_run("runB", db_path=db_path)
        assert removed == 2
        runs = dict(crawl.list_runs(db_path=db_path))
        assert "runA" in runs
        assert "runB" not in runs
