"""Tests for the markdown pruning heuristic (ENH-003).

The heuristic is a pure function over the converted page markdown; these tests
cover each rule and its keep-bias guards. A final test exercises the
``process_url`` wiring to prove the pruned markdown (not the raw) reaches the
LLM when ``--prune`` is set.
"""

import pytest

from par_scrape.prune import prune_markdown


def test_empty_input_returns_empty():
    assert prune_markdown("") == ""


def test_nav_block_of_six_link_items_is_removed():
    nav = "\n".join(f"- [{label}](/)" for label in ["Home", "About", "Docs", "Blog", "Careers", "Login"])
    body = f"# Welcome\n\n{nav}\n\nReal content here."
    pruned = prune_markdown(body)
    # Every nav label's link is gone, the heading and the real content survive.
    assert "[Home](/)" not in pruned
    assert "[Login](/)" not in pruned
    assert "# Welcome" in pruned
    assert "Real content here." in pruned


def test_list_item_with_price_is_kept():
    line = "- [Product X](https://example.com/x) — $49.99"
    assert line in prune_markdown(line)


def test_run_of_three_link_items_is_kept():
    # Below the rule-2 threshold of four; nothing is dropped.
    nav = "\n".join(f"- [{label}](/)" for label in ["Home", "About", "Docs"])
    assert nav in prune_markdown(nav)


@pytest.mark.parametrize(
    "block",
    [
        "| Model | Price |\n|---|---|\n| A | 1 |",
        "```python\nx = 1\nprint(x)\n```",
    ],
)
def test_tables_and_code_fences_are_byte_identical(block):
    assert prune_markdown(block) == block


def test_headings_are_kept():
    body = "# Title\n\n## Subtitle\n\nparagraph"
    assert prune_markdown(body) == body


def test_five_blank_lines_collapse_to_one():
    body = "first\n\n\n\n\n\nsecond"
    assert prune_markdown(body) == "first\n\nsecond"


def test_bare_url_line_is_dropped():
    # Digit-free URL on its own line is boilerplate.
    body = "intro\n\nhttps://example.com/path\n\nmore"
    pruned = prune_markdown(body)
    assert "https://example.com/path" not in pruned
    assert "intro" in pruned
    assert "more" in pruned


def test_image_only_line_is_dropped():
    body = "intro\n\n![alt](/img.png)\n\nmore"
    pruned = prune_markdown(body)
    assert "![alt](/img.png)" not in pruned


def test_digit_protected_link_item_is_kept():
    # A nav link that carries a digit (price/spec) is preserved even in a run.
    nav = "\n".join(
        [
            "- [Home](/)",
            "- [Plan 2](/plans)",
            "- [Plan 3](/plans)",
            "- [Plan 4](/plans)",
            "- [Plan 5](/plans)",
        ]
    )
    pruned = prune_markdown(nav)
    assert "[Plan 2](/plans)" in pruned


def test_process_url_feeds_pruned_markdown_to_llm(tmp_path, db_path, mocker):
    """With config.prune set, format_data receives the pruned markdown."""
    from par_ai_core.llm_providers import LlmProvider
    from par_ai_core.pricing_lookup import PricingDisplay
    from par_ai_core.web_tools import ScraperChoice, ScraperWaitType

    from par_scrape.crawl import add_to_queue
    from par_scrape.enums import CleanupType, CrawlType, OutputFormat
    from par_scrape.runner import ScrapeConfig, process_url

    nav = "\n".join(f"- [{label}](/)" for label in ["Home", "About", "Docs", "Blog", "Careers", "Login"])
    # html_to_markdown is patched, so what it returns IS the markdown the pruner
    # sees. Keep the nav block and the real content on separate lines.
    markdown = f"# Page\n\n{nav}\n\nKeep me: widget\n"
    page = f"<html><body>{nav}</body></html>"

    mocker.patch("par_scrape.runner.html_to_markdown", side_effect=lambda raw, **_kw: markdown)

    captured: dict[str, str] = {}

    def fake_format_data(*, data, **_kw):
        captured["data"] = data
        result = mocker.MagicMock()
        result.listings = [{"x": "y"}]
        return result

    mocker.patch("par_scrape.runner.format_data", side_effect=fake_format_data)
    mocker.patch("par_scrape.runner.save_formatted_data", return_value=(None, {}))

    config = ScrapeConfig(
        url="https://example.com/page",
        output_format=[OutputFormat.JSON],
        fields=["Model"],
        scraper=ScraperChoice.PLAYWRIGHT,
        scrape_retries=3,
        scrape_max_parallel=1,
        run_name="prune-wiring",
        output_folder=tmp_path,
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
        prune=True,
    )
    add_to_queue(config.run_name, [config.url], db_path=db_path)

    process_url(
        config.url,
        page,
        config,
        cb=mocker.MagicMock(),
        status=mocker.MagicMock(),
        llm_needed=True,
        llm_config=mocker.MagicMock(),
        dynamic_model_container=mocker.MagicMock(),
    )

    assert "[Home](/" not in captured["data"]
    assert "Keep me: widget" in captured["data"]
