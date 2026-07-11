"""Tests for the crawl orchestration layer (ARC-002 / QA-007).

Covers ``process_url`` (happy path + error classification) and a CLI smoke test.
All tests are fully offline: ``fetch_url`` and ``html_to_markdown`` are patched
where they are *used* (``par_scrape.runner``), and every DB touch goes through
the conftest ``db_path`` fixture so ``~/.par_scrape/jobs.sqlite`` is never read
or written.
"""

import sqlite3
import time
from contextlib import closing
from pathlib import Path

from par_ai_core.llm_providers import LlmProvider
from par_ai_core.pricing_lookup import PricingDisplay
from par_ai_core.web_tools import ScraperChoice, ScraperWaitType
from typer.testing import CliRunner

from par_scrape.__main__ import app
from par_scrape.crawl import PageStatus, add_to_queue, get_queue_stats
from par_scrape.enums import CleanupType, CrawlType, ErrorType, OutputFormat
from par_scrape.runner import ScrapeConfig, process_url, run_crawl
from par_scrape.scrape_data import create_container_model, create_dynamic_model


def _make_config(output_folder: Path, **overrides) -> ScrapeConfig:
    """Build a minimal markdown-only single-page ScrapeConfig for tests.

    Defaults describe a no-LLM, single-page, silent run; any field can be
    overridden via ``overrides``.
    """
    defaults: dict = dict(
        url="https://example.com/testpage",
        output_format=[OutputFormat.MARKDOWN],
        fields=["Model"],
        scraper=ScraperChoice.PLAYWRIGHT,
        scrape_retries=3,
        scrape_max_parallel=1,
        run_name="runner-test",
        output_folder=output_folder,
        cleanup=CleanupType.NONE,
        crawl_type=CrawlType.SINGLE_PAGE,
        crawl_batch_size=1,
        crawl_max_pages=1,
        respect_robots=False,
        respect_rate_limits=False,
        crawl_delay=1,
        wait_type=ScraperWaitType.SLEEP,
        wait_selector=None,
        headless=True,
        sleep_time=0,
        ai_provider=LlmProvider.OPENAI,
        model=None,
        ai_base_url=None,
        prompt_cache=False,
        reasoning_effort=None,
        reasoning_budget=None,
        display_output=None,
        silent=True,
        pricing=PricingDisplay.NONE,
        extraction_prompt=None,
        if_changed=False,
        prune=False,
    )
    defaults.update(overrides)
    return ScrapeConfig(**defaults)


# ---------- process_url: happy path ----------


def test_process_url_markdown_only_marks_complete_and_writes_file(tmp_path, db_path, mocker):
    """QA-007: a markdown-only run records COMPLETED and writes the raw file."""
    # Patch html_to_markdown WHERE IT IS USED (runner module), not its origin.
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: raw)

    config = _make_config(output_folder=tmp_path)
    cb = mocker.MagicMock()
    status = mocker.MagicMock()

    # The URL must be queued first so mark_complete has a row to update.
    add_to_queue(config.run_name, [config.url], db_path=db_path)

    process_url(
        config.url,
        "<html><body><p>hello world</p></body></html>",
        config,
        cb=cb,
        status=status,
        llm_needed=False,
        llm_config=None,
        dynamic_model_container=None,
    )

    # The row reached mark_complete.
    stats = get_queue_stats(config.run_name, db_path=db_path)
    assert stats[PageStatus.COMPLETED.value] == 1
    assert stats[PageStatus.ERROR.value] == 0

    # The raw markdown file was written under the run's output folder.
    raw_files = list(tmp_path.rglob("*raw*.md"))
    assert raw_files, f"no raw markdown file written under {tmp_path}"
    assert "hello world" in raw_files[0].read_text(encoding="utf-8")


# ---------- process_url: error path ----------


def test_process_url_html_to_markdown_timeout_marks_error(tmp_path, db_path, mocker):
    """QA-007: a TimeoutError from html_to_markdown is classified and marked ERROR/TIMEOUT."""
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=TimeoutError("fetch timed out"))

    config = _make_config(output_folder=tmp_path)
    cb = mocker.MagicMock()
    status = mocker.MagicMock()

    add_to_queue(config.run_name, [config.url], db_path=db_path)

    # process_url swallows per-URL exceptions (routes them to mark_error), so it
    # must return normally rather than propagate.
    process_url(
        config.url,
        "<html><body>hi</body></html>",
        config,
        cb=cb,
        status=status,
        llm_needed=False,
        llm_config=None,
        dynamic_model_container=None,
    )

    with closing(sqlite3.connect(db_path)) as conn, conn:
        row = conn.execute(
            "SELECT status, error_type FROM scrape WHERE ticket_id = ? AND url = ?",
            (config.run_name, config.url),
        ).fetchone()

    assert row is not None
    assert row[0] == PageStatus.ERROR.value
    assert row[1] == ErrorType.TIMEOUT.value


# ---------- CLI smoke test ----------


def test_cli_markdown_only_smoke(tmp_path, db_path, mocker):
    """QA-007: markdown-only CLI run is fully offline, exits 0, and writes output.

    Patches ``fetch_url`` and ``html_to_markdown`` at their use site in the
    runner, and ``_startup`` so the home ``~/.par_scrape.env`` is untouched.
    The conftest ``db_path`` fixture redirects the queue DB to tmp_path.
    """
    canned_html = "<html><body><p>smoke test content</p></body></html>"
    mocker.patch("par_scrape.__main__._startup", lambda: None)
    mocker.patch("par_scrape.runner.fetch_url", return_value=[canned_html])
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: raw)

    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--url",
            "https://example.com",
            "--output-format",
            "md",
            "--output-folder",
            str(out_dir),
            "--crawl-type",
            "single_page",
        ],
    )

    assert result.exit_code == 0, f"CLI failed (exit {result.exit_code}):\n{result.output}"
    raw_files = list(out_dir.rglob("*raw*.md"))
    assert raw_files, f"no raw markdown file written under {out_dir}"
    assert "smoke test content" in raw_files[0].read_text(encoding="utf-8")


# ---------- ENH-001: concurrent extraction ----------


def test_run_crawl_concurrent_pool_processes_pages_in_parallel(tmp_path, db_path, mocker):
    """ENH-001: with scrape_max_parallel>1, per-URL processing overlaps across the batch.

    ``html_to_markdown`` sleeps ``sleep_seconds`` per page; 8 pages through a
    4-worker pool finish in ~2 waves (~0.4s) rather than the serialized
    ``8 * sleep_seconds`` (~1.6s). Fetch and the LLM are patched out; the queue
    DB is the conftest tmp fixture.
    """
    sleep_seconds = 0.2
    page_count = 8

    def fake_html_to_markdown(raw, **_kw):
        time.sleep(sleep_seconds)
        return raw

    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=fake_html_to_markdown)
    mocker.patch(
        "par_scrape.runner.fetch_url", side_effect=lambda urls, **_kw: ["<html><body>p</body></html>"] * len(urls)
    )

    urls = [f"https://example.com/page{i}" for i in range(page_count)]
    config = _make_config(
        output_folder=tmp_path,
        url=urls[0],
        run_name="enh001-concurrent",
        crawl_type=CrawlType.SINGLE_PAGE,
        crawl_batch_size=page_count,
        crawl_max_pages=page_count,
        scrape_max_parallel=4,
        respect_rate_limits=False,
        silent=True,
    )

    # Seed the queue with every page (the primary url is among them, so the
    # add_to_queue([primary]) inside run_crawl is a no-op INSERT OR IGNORE).
    add_to_queue(config.run_name, urls, db_path=db_path)

    start = time.time()
    exit_code = run_crawl(config)
    elapsed = time.time() - start

    assert exit_code == 0
    stats = get_queue_stats(config.run_name, db_path=db_path)
    assert stats[PageStatus.COMPLETED.value] == page_count
    assert stats[PageStatus.ERROR.value] == 0
    # Pure sleeping alone costs page_count * sleep_seconds when serialized;
    # finishing below that bound proves the pool overlapped the work.
    assert elapsed < page_count * sleep_seconds, f"elapsed {elapsed:.2f}s was not parallel"


def test_run_crawl_concurrent_pool_isolates_per_url_errors(tmp_path, db_path, mocker):
    """ENH-001: one page failing inside the pool does not abort the batch.

    8 pages, 4 workers; the page at ``fail_url`` raises ``TimeoutError`` from
    ``html_to_markdown``. The other 7 complete; the failure is recorded
    ``ERROR`` / ``TIMEOUT`` and ``run_crawl`` still returns 0.
    """
    fail_url = "https://example.com/page-fail"

    def fake_html_to_markdown(raw, url=None, **_kw):
        if url == fail_url:
            raise TimeoutError("fetch timed out")
        time.sleep(0.05)
        return raw

    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=fake_html_to_markdown)
    mocker.patch(
        "par_scrape.runner.fetch_url", side_effect=lambda urls, **_kw: ["<html><body>p</body></html>"] * len(urls)
    )

    ok_urls = [f"https://example.com/ok{i}" for i in range(7)]
    urls = ok_urls + [fail_url]
    config = _make_config(
        output_folder=tmp_path,
        url=ok_urls[0],
        run_name="enh001-error-iso",
        crawl_type=CrawlType.SINGLE_PAGE,
        crawl_batch_size=len(urls),
        crawl_max_pages=len(urls),
        scrape_max_parallel=4,
        respect_rate_limits=False,
        silent=True,
    )

    add_to_queue(config.run_name, urls, db_path=db_path)

    exit_code = run_crawl(config)

    assert exit_code == 0
    stats = get_queue_stats(config.run_name, db_path=db_path)
    assert stats[PageStatus.COMPLETED.value] == 7
    assert stats[PageStatus.ERROR.value] == 1

    with closing(sqlite3.connect(db_path)) as conn, conn:
        row = conn.execute(
            "SELECT error_type FROM scrape WHERE ticket_id = ? AND url = ?",
            (config.run_name, fail_url),
        ).fetchone()
    assert row is not None
    assert row[0] == ErrorType.TIMEOUT.value


# ---------- ENH-002: incremental re-scrape ----------

_TEST_URL = "https://example.com/testpage"


def _extracted_container():
    """A real DynamicListingsContainer instance the mocked ``format_data`` returns.

    ``process_url`` checks ``formatted_data.listings`` is non-empty and then
    passes the instance to the real ``save_formatted_data``, so it must be a
    genuine pydantic object that writes a real ``extracted_data.json`` for the
    reuse path to copy.
    """
    container_cls = create_container_model(create_dynamic_model(["title"]))
    return container_cls(listings=[{"title": "sample"}])


def _run_process_url_llm(tmp_path, db_path, mocker, run_name, raw_html):
    """Run ``process_url`` once for a JSON/LLM single-page URL under ``run_name``.

    ``format_data``, ``html_to_markdown``, and ``show_llm_cost`` are patched at
    their use site in the runner. ``format_data`` is the only one whose call
    count matters: it stands in for the billed LLM round trip.
    """
    cfg = _make_config(
        output_folder=tmp_path,
        run_name=run_name,
        url=_TEST_URL,
        output_format=[OutputFormat.JSON],
        fields=["title"],
        crawl_type=CrawlType.SINGLE_PAGE,
        if_changed=True,
    )
    container_cls = create_container_model(create_dynamic_model(["title"]))
    add_to_queue(run_name, [cfg.url], db_path=db_path)
    process_url(
        cfg.url,
        raw_html,
        cfg,
        cb=mocker.MagicMock(),
        status=mocker.MagicMock(),
        llm_needed=True,
        llm_config=mocker.MagicMock(),
        dynamic_model_container=container_cls,
    )
    return cfg


def test_process_url_if_changed_skips_unchanged_page(tmp_path, db_path, mocker):
    """ENH-002: a second run with identical markdown reuses the first run's outputs.

    Two runs under different run_names with the same canned HTML produce the same
    content hash; the second run must NOT call ``format_data`` (the billed LLM
    step) and must surface run-a's extracted JSON in its own output folder.
    """
    fmt_mock = mocker.patch("par_scrape.runner.format_data", return_value=_extracted_container())
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: raw)
    mocker.patch("par_scrape.runner.show_llm_cost")

    html = "<html><body><p>same content</p></body></html>"
    _run_process_url_llm(tmp_path, db_path, mocker, "run-a", html)
    _run_process_url_llm(tmp_path, db_path, mocker, "run-b", html)

    assert fmt_mock.call_count == 1  # only run-a paid for extraction
    run_b_json = tmp_path / "run-b" / "example.com" / "testpage" / "extracted_data.json"
    assert run_b_json.exists(), "run-b should have reused run-a's extracted JSON"


def test_process_url_if_changed_reextracts_when_content_changes(tmp_path, db_path, mocker):
    """ENH-002: changed markdown -> different hash -> no prior match -> re-extract.

    Both runs pay for extraction (``format_data`` called twice).
    """
    fmt_mock = mocker.patch("par_scrape.runner.format_data", return_value=_extracted_container())
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: raw)
    mocker.patch("par_scrape.runner.show_llm_cost")

    _run_process_url_llm(tmp_path, db_path, mocker, "run-a", "<html><body>AAA</body></html>")
    _run_process_url_llm(tmp_path, db_path, mocker, "run-b", "<html><body>BBB</body></html>")

    assert fmt_mock.call_count == 2


def test_process_url_if_changed_falls_through_when_prior_output_missing(tmp_path, db_path, mocker):
    """ENH-002: a missing prior output file must degrade gracefully to extraction.

    The hash matches a prior completed row, but that run's extracted JSON has
    since been deleted. ``_copy_prior_outputs`` returns None and run-b re-extracts
    rather than silently producing no output.
    """
    fmt_mock = mocker.patch("par_scrape.runner.format_data", return_value=_extracted_container())
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: raw)
    mocker.patch("par_scrape.runner.show_llm_cost")

    html = "<html><body><p>same content</p></body></html>"
    _run_process_url_llm(tmp_path, db_path, mocker, "run-a", html)

    run_a_json = tmp_path / "run-a" / "example.com" / "testpage" / "extracted_data.json"
    assert run_a_json.exists()
    run_a_json.unlink()  # simulate the prior run's output being cleaned up

    _run_process_url_llm(tmp_path, db_path, mocker, "run-b", html)

    assert fmt_mock.call_count == 2  # could not reuse, re-extracted


def test_process_url_if_changed_off_by_default(tmp_path, db_path, mocker):
    """ENH-002: without --if-changed, an unchanged page is re-extracted every run.

    Guards against the reuse path firing when the flag was never set.
    """
    fmt_mock = mocker.patch("par_scrape.runner.format_data", return_value=_extracted_container())
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: raw)
    mocker.patch("par_scrape.runner.show_llm_cost")

    html = "<html><body><p>same content</p></body></html>"
    # Build configs explicitly with if_changed=False (the _make_config default).
    for run_name in ("run-a", "run-b"):
        cfg = _make_config(
            output_folder=tmp_path,
            run_name=run_name,
            url=_TEST_URL,
            output_format=[OutputFormat.JSON],
            fields=["title"],
            crawl_type=CrawlType.SINGLE_PAGE,
            if_changed=False,
        )
        container_cls = create_container_model(create_dynamic_model(["title"]))
        add_to_queue(run_name, [cfg.url], db_path=db_path)
        process_url(
            cfg.url,
            html,
            cfg,
            cb=mocker.MagicMock(),
            status=mocker.MagicMock(),
            llm_needed=True,
            llm_config=mocker.MagicMock(),
            dynamic_model_container=container_cls,
        )

    assert fmt_mock.call_count == 2  # no reuse: both runs extracted
