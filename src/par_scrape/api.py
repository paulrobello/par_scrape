"""Public library API for par_scrape (ENH-005).

A small, typed, documented programmatic entry point so the package can be used
from pipelines, notebooks, and other agents without shelling out to the CLI.
The wheel already ships ``py.typed`` and a "Libraries" classifier; this module
makes that claim true.

Provisional for one release: signatures may change before stabilization.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from par_ai_core.llm_providers import LlmProvider
from par_ai_core.pricing_lookup import PricingDisplay

from par_scrape.enums import CrawlType, OutputFormat, PageStatus
from par_scrape.exceptions import CrawlConfigError, ProviderConfigError
from par_scrape.queue_db import get_run_pages
from par_scrape.runner import build_config, run_crawl

# Output formats whose structured extraction requires an LLM call.
_LLM_FORMATS = frozenset({OutputFormat.JSON, OutputFormat.CSV, OutputFormat.EXCEL})


@dataclass(frozen=True)
class PageResult:
    """The outcome of scraping a single page within a run.

    Attributes:
        url: The page URL.
        status: Terminal queue status (typically COMPLETED or ERROR).
        error_message: The recorded error message when ``status`` is ERROR,
            otherwise ``None``.
        file_paths: Map of each written output format to its path. For a
            Markdown-only run this contains ``OutputFormat.MARKDOWN`` pointing
            at the saved raw Markdown.
    """

    url: str
    status: PageStatus
    error_message: str | None
    file_paths: dict[OutputFormat, Path]


@dataclass(frozen=True)
class ScrapeResult:
    """The outcome of a :func:`scrape` call.

    Attributes:
        run_name: The run identifier (resolved when not supplied).
        output_folder: The run's output directory under ``output_folder``.
        pages: One :class:`PageResult` per page processed, in queue order.
    """

    run_name: str
    output_folder: Path
    pages: list[PageResult]

    @property
    def ok(self) -> bool:
        """True when every page reached COMPLETED."""
        return all(page.status == PageStatus.COMPLETED for page in self.pages)


def _resolve_provider(name: str) -> LlmProvider:
    """Map a provider name (case-insensitive) to an :class:`LlmProvider`."""
    try:
        return LlmProvider(name)
    except ValueError:
        pass
    lowered = name.lower()
    for member in LlmProvider:
        if member.value.lower() == lowered:
            return member
    raise ProviderConfigError(f"Unknown AI provider {name!r}")


def _parse_file_paths(raw: str | None) -> dict[OutputFormat, Path]:
    """Parse a row's ``file_paths`` JSON string into a typed map."""
    result: dict[OutputFormat, Path] = {}
    if not raw:
        return result
    try:
        mapping = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return result
    for key, value in mapping.items():
        try:
            result[OutputFormat(key)] = Path(value)
        except ValueError:
            continue
    return result


def _page_result(row: Any) -> PageResult:
    """Build a :class:`PageResult` from a ``scrape`` queue row."""
    return PageResult(
        url=row["url"],
        status=PageStatus(row["status"]),
        error_message=row["error_msg"],
        file_paths=_parse_file_paths(row["file_paths"]),
    )


def scrape(
    url: str,
    *,
    fields: Sequence[str] | None = None,
    output_formats: Sequence[OutputFormat] = (OutputFormat.MARKDOWN,),
    ai_provider: str | None = None,
    model: str | None = None,
    crawl_type: CrawlType = CrawlType.SINGLE_PAGE,
    max_pages: int = 1,
    output_folder: Path | None = None,
    run_name: str | None = None,
    quiet: bool = True,
    **advanced: Any,
) -> ScrapeResult:
    """Scrape ``url`` and return a structured result (provisional API).

    Markdown-only by default (``output_formats=(OutputFormat.MARKDOWN,)`` with no
    ``ai_provider``): no LLM is used and no API key is required. Pass an
    ``ai_provider`` together with an LLM output format (json/csv/excel) for
    structured extraction; provider API keys must be present in the environment
    (this library function does not load ``~/.par_scrape.env``).

    Configuration problems (unknown provider, LLM format requested without a
    provider, missing API key) raise :class:`ProviderConfigError` /
    :class:`CrawlConfigError`. Per-page failures do not raise — they surface as
    :class:`PageResult` entries with ``status == PageStatus.ERROR``.

    Args:
        url: The URL to scrape.
        fields: Fields to extract (LLM runs only). Defaults to the standard
            pricing fields.
        output_formats: Output formats to write. Defaults to Markdown only.
        ai_provider: Provider name (e.g. ``"openai"``) for LLM extraction, or
            ``None`` for a Markdown-only run.
        model: Model name; defaults to the provider's default model.
        crawl_type: Crawl strategy; defaults to a single page.
        max_pages: Maximum pages to crawl this run (default 1).
        output_folder: Base output directory (default ``./output``).
        run_name: Run identifier; defaults to a timestamp.
        quiet: Suppress console output (default ``True``).
        **advanced: Pass-through :class:`~par_scrape.runner.ScrapeConfig` fields
            (e.g. ``scraper``, ``wait_type``, ``scrape_retries``,
            ``respect_robots``, ``prune``).

    Returns:
        A :class:`ScrapeResult` describing the run and each page.

    Raises:
        ProviderConfigError: When ``ai_provider`` is not a known provider.
        CrawlConfigError: When an LLM format is requested without a provider, or
            the crawl is otherwise misconfigured.
    """
    provider = _resolve_provider(ai_provider) if ai_provider is not None else None
    formats = list(output_formats)
    if provider is None and any(fmt in _LLM_FORMATS for fmt in formats):
        raise CrawlConfigError("ai_provider is required when an LLM output format (json/csv/excel) is requested.")

    config = build_config(
        url=url,
        output_format=formats,
        fields=list(fields) if fields is not None else None,
        ai_provider=provider,
        model=model,
        crawl_type=crawl_type,
        crawl_max_pages=max_pages,
        output_folder=output_folder if output_folder is not None else Path("./output"),
        run_name=run_name if run_name is not None else "",
        silent=quiet,
        pricing=PricingDisplay.NONE if quiet else PricingDisplay.DETAILS,
        display_output=None,
        **advanced,
    )
    resolved_run_name = config.run_name

    try:
        run_crawl(config)
    except typer.Exit as exc:
        # validate_llm_options signals config failures (e.g. a missing API key)
        # via typer.Exit; surface those as the library's typed config error.
        raise CrawlConfigError(f"Crawl configuration error (exit code {exc.exit_code}).") from exc

    pages = [_page_result(row) for row in get_run_pages(resolved_run_name)]
    return ScrapeResult(
        run_name=resolved_run_name,
        output_folder=config.output_folder / resolved_run_name,
        pages=pages,
    )
