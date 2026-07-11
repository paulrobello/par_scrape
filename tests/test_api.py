"""Tests for the public library API (ENH-005).

All offline: ``fetch_url`` and ``html_to_markdown`` are patched at their use
site (``par_scrape.runner``), and the conftest ``db_path`` fixture redirects the
queue DB to a tmp path so ``~/.par_scrape/jobs.sqlite`` is never touched.
"""

import pytest

from par_scrape import PageResult, ScrapeResult, scrape
from par_scrape.enums import OutputFormat, PageStatus
from par_scrape.exceptions import CrawlConfigError, ProviderConfigError

CANNED_HTML = "<html><body><p>real content</p></body></html>"


def _patch_fetch(mocker, html: str = CANNED_HTML):
    mocker.patch("par_scrape.runner.fetch_url", return_value=[html])
    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: raw)


def test_scrape_is_callable():
    assert callable(scrape)


def test_scrape_markdown_only_writes_file_and_returns_result(tmp_path, db_path, mocker):
    _patch_fetch(mocker)
    result = scrape("https://example.com/page", output_folder=tmp_path)

    assert isinstance(result, ScrapeResult)
    assert result.ok
    assert len(result.pages) == 1
    page = result.pages[0]
    assert isinstance(page, PageResult)
    assert page.status == PageStatus.COMPLETED
    assert page.error_message is None
    assert OutputFormat.MARKDOWN in page.file_paths
    assert page.file_paths[OutputFormat.MARKDOWN].exists()
    assert "real content" in page.file_paths[OutputFormat.MARKDOWN].read_text(encoding="utf-8")


def test_scrape_quiet_produces_no_stdout(tmp_path, db_path, mocker, capsys):
    _patch_fetch(mocker)
    scrape("https://example.com/page", output_folder=tmp_path, quiet=True)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_scrape_bad_provider_raises(tmp_path, db_path):
    with pytest.raises(ProviderConfigError):
        scrape(
            "https://example.com/page",
            ai_provider="not_a_real_provider",
            output_formats=[OutputFormat.JSON],
            output_folder=tmp_path,
        )


def test_scrape_llm_format_without_provider_raises(tmp_path, db_path):
    with pytest.raises(CrawlConfigError):
        scrape("https://example.com/page", output_formats=[OutputFormat.JSON], output_folder=tmp_path)


def test_scrape_fetch_error_surfaces_as_error_page(tmp_path, db_path, mocker):
    mocker.patch("par_scrape.runner.fetch_url", side_effect=RuntimeError("network down"))
    result = scrape("https://example.com/page", output_folder=tmp_path)

    assert not result.ok
    assert len(result.pages) == 1
    page = result.pages[0]
    assert page.status == PageStatus.ERROR
    assert page.error_message
