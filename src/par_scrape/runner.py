"""Crawl orchestration for par_scrape.

This module contains the orchestration layer split out of ``__main__.py`` (ARC-002).
The CLI layer parses options and builds a :class:`ScrapeConfig`; everything below
(validation, banner display, per-URL processing, and the crawl loop) lives here so
it can be tested in isolation.
"""

import hashlib
import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import typer
from par_ai_core.llm_config import LlmConfig, ReasoningEffort
from par_ai_core.llm_providers import (
    LlmProvider,
    provider_default_models,
    provider_env_key_names,
)
from par_ai_core.output_utils import DisplayOutputFormat, display_formatted_output
from par_ai_core.par_logging import console_out
from par_ai_core.pricing_lookup import PricingDisplay, show_llm_cost
from par_ai_core.provider_cb_info import ParAICallbackHandler, get_parai_callback
from par_ai_core.web_tools import ScraperChoice, ScraperWaitType, fetch_url, html_to_markdown
from pydantic import BaseModel
from rich.markup import escape
from rich.panel import Panel
from rich.status import Status
from rich.text import Text

from par_scrape import __application_title__, __version__
from par_scrape.crawl import (
    CrawlType,
    PageStatus,
    add_to_queue,
    extract_links,
    find_completed_by_hash,
    get_next_urls,
    get_queue_stats,
    get_url_depth,
    get_url_output_folder,
    increase_crawl_delay,
    init_db,
    mark_complete,
    mark_error,
    set_crawl_delay,
)
from par_scrape.enums import CleanupType, ErrorType, OutputFormat
from par_scrape.exceptions import ScrapeError, classify_error
from par_scrape.queue_db import close_connections
from par_scrape.scrape_data import (
    create_container_model,
    create_dynamic_model,
    format_data,
    save_formatted_data,
    save_raw_data,
)

# Next.js renders this exact sentence when a client-side exception crashes the
# page. Matching the full marker (against raw HTML, before markdown conversion)
# avoids false positives on pages that merely contain the words "Application
# error" and routes the failure through classify_error via ScrapeError.
NEXTJS_CLIENT_ERROR_MARKER = "Application error: a client-side exception has occurred"

# Serializes Rich console output across worker threads (ENH-001). Uncontended on
# the workers==1 path, so default output ordering is byte-for-byte unchanged.
_console_lock = threading.Lock()


def _print_locked(*args: Any, **kwargs: Any) -> None:
    """``console_out.print`` serialized under :data:`_console_lock`.

    Worker threads in the concurrent extraction pool route every console write
    through here so multi-line output never interleaves. The lock is also taken
    on the single-worker path, but uncontended, so behavior is identical.
    """
    with _console_lock:
        console_out.print(*args, **kwargs)


@dataclass(frozen=True)
class ScrapeConfig:
    """Every value the crawl loop derives from the CLI options.

    Built once in ``__main__.main`` and passed unchanged into the orchestrator.
    Values that ``main`` computes (run-name sanitization, URL trailing-slash trim)
    are stored here already resolved so the loop can use them directly.
    """

    url: str
    output_format: list[OutputFormat]
    fields: list[str]
    scraper: ScraperChoice
    scrape_retries: int
    scrape_max_parallel: int
    run_name: str
    output_folder: Path
    cleanup: CleanupType
    crawl_type: CrawlType
    crawl_batch_size: int
    crawl_max_pages: int
    respect_robots: bool
    respect_rate_limits: bool
    crawl_delay: int
    wait_type: ScraperWaitType
    wait_selector: str | None
    headless: bool
    sleep_time: int
    ai_provider: LlmProvider
    model: str | None
    ai_base_url: str | None
    prompt_cache: bool
    reasoning_effort: ReasoningEffort | None
    reasoning_budget: int | None
    display_output: DisplayOutputFormat | None
    silent: bool
    pricing: PricingDisplay
    extraction_prompt: Path | None
    if_changed: bool


def _remove_run_output(output_folder: Path, run_name: str) -> None:
    """Delete only this run's output subtree, refusing unsafe targets."""
    target = (output_folder / run_name).resolve()
    if not target.is_dir():
        return
    if target in (Path.home().resolve(), Path("/").resolve()) or run_name not in target.name:
        console_out.print(f"[bold red]Refusing to remove suspicious path: {target}[/bold red]")
        return
    shutil.rmtree(target)
    console_out.print(f"[bold green]Removed run output folder: {target}[/bold green]")


def validate_llm_options(
    config: ScrapeConfig,
) -> tuple[bool, str | None, LlmConfig | None, type[BaseModel] | None]:
    """Validate provider/model/key selection and build the LLM config + dynamic model.

    Mirrors the validation block that previously lived at the top of ``main``.
    Raises ``typer.Exit(1)`` on invalid selection (preserved verbatim from the
    pre-refactor behavior; QA-004 may later convert these to a return code).

    Args:
        config: The fully-resolved scrape configuration.

    Returns:
        A ``(llm_needed, resolved_model, llm_config, dynamic_model_container)``
        tuple. When LLM extraction is not required the latter three are ``None``.
    """
    outputs_needing_llm = [OutputFormat.JSON, OutputFormat.CSV, OutputFormat.EXCEL]
    llm_needed = any(format in config.output_format for format in outputs_needing_llm)
    model = config.model
    if llm_needed:
        if not model:
            model = provider_default_models[config.ai_provider]

        if config.ai_provider not in [LlmProvider.OLLAMA, LlmProvider.BEDROCK, LlmProvider.LITELLM]:
            key_name = provider_env_key_names[config.ai_provider]
            if not os.environ.get(key_name):
                console_out.print(f"[bold red]{key_name} environment variable not set. Exiting...[/bold red]")
                raise typer.Exit(1)

        if config.prompt_cache and config.ai_provider != LlmProvider.ANTHROPIC:
            console_out.print(
                "[bold red]Prompt cache flag is only available for Anthropic provider. Exiting...[/bold red]"
            )
            raise typer.Exit(1)

        console_out.print("[bold cyan]Creating llm config and dynamic models...")
        llm_config = LlmConfig(
            provider=config.ai_provider,
            model_name=model,
            temperature=0,
            base_url=config.ai_base_url,
            reasoning_effort=config.reasoning_effort,
            reasoning_budget=config.reasoning_budget,
        )
        dynamic_extraction_model = create_dynamic_model(config.fields)
        dynamic_model_container = create_container_model(dynamic_extraction_model)
    else:
        llm_config = None
        dynamic_model_container = None

    return llm_needed, model, llm_config, dynamic_model_container


def print_config_panels(config: ScrapeConfig, model: str | None, llm_needed: bool) -> None:
    """Render the AI configuration and scraping configuration Rich panels."""
    if llm_needed:
        console_out.print(
            Panel.fit(
                Text.assemble(
                    ("AI Provider: ", "cyan"),
                    (f"{config.ai_provider.value}", "green"),
                    "\n",
                    ("Model: ", "cyan"),
                    (f"{model}", "green"),
                    "\n",
                    ("AI Provider Base URL: ", "cyan"),
                    (f"{config.ai_base_url or 'default'}", "green"),
                    "\n",
                    ("Prompt Cache: ", "cyan"),
                    (f"{config.prompt_cache}", "green"),
                    "\n",
                    ("Fields to extract: ", "cyan"),
                    (", ".join(config.fields), "green"),
                    "\n",
                    ("Pricing Display: ", "cyan"),
                    (f"{config.pricing.value}", "green"),
                ),
                title="[bold]AI Configuration",
                border_style="bold",
            )
        )

    console_out.print(
        Panel.fit(
            Text.assemble(
                ("Primary URL: ", "cyan"),
                (f"{config.url}", "green"),
                "\n",
                ("Scraper: ", "cyan"),
                (f"{config.scraper}", "green"),
                "\n",
                ("Scrape Max Parallel: ", "cyan"),
                (f"{config.scrape_max_parallel}", "green"),
                "\n",
                ("Retries: ", "cyan"),
                (
                    f"{config.scrape_retries}",
                    "green",
                ),
                "\n",
                ("Crawl Type: ", "cyan"),
                (f"{config.crawl_type.value}", "green"),
                "\n",
                ("Crawl Batch Size: ", "cyan"),
                (f"{config.crawl_batch_size}", "green"),
                "\n",
                ("Respect Rate Limits: ", "cyan"),
                (f"{config.respect_rate_limits}", "green"),
                "\n",
                ("Default Crawl Delay: ", "cyan"),
                (f"{config.crawl_delay} seconds", "green"),
                "\n",
                ("Output Format: ", "cyan"),
                (", ".join([f"{format.value}" for format in config.output_format]), "green"),
                "\n",
                ("Max Pages: ", "cyan"),
                (f"{config.crawl_max_pages}", "green"),
                "\n",
                ("Headless: ", "cyan"),
                (f"{config.headless}", "green"),
                "\n",
                ("Wait Type: ", "cyan"),
                (f"{config.wait_type.value}", "green"),
                "\n",
                ("Wait Selector: ", "cyan"),
                (
                    f"{config.wait_selector if config.wait_type in (ScraperWaitType.SELECTOR, ScraperWaitType.TEXT) else 'N/A'}",
                    "green",
                ),
                "\n",
                ("Sleep Time: ", "cyan"),
                (
                    f"{config.sleep_time} seconds",
                    "green",
                ),
                "\n",
                ("Display output: ", "cyan"),
                (f"{config.display_output or 'None'}", "green"),
                "\n",
                ("Silent mode: ", "cyan"),
                (f"{config.silent}", "green"),
                "\n",
                ("Cleanup: ", "cyan"),
                (f"{config.cleanup}", "green"),
            ),
            title="[bold]Scraping Configuration",
            border_style="bold",
        )
    )


def _copy_prior_outputs(
    prior: dict[str, str | None],
    url_output_folder: Path,
    output_formats: list[OutputFormat],
) -> dict[OutputFormat, Path] | None:
    """Copy a prior run's extracted outputs into this run's URL folder.

    ENH-002 reuse step: when a page's markdown hash matches a prior completed
    run, that run's output files are copied (same basenames) into the current
    run's ``url_output_folder`` so the crawl result is identical without paying
    for LLM extraction.

    Args:
        prior: A ``find_completed_by_hash`` result carrying the prior row's
            ``file_paths`` JSON string.
        url_output_folder: The current run's output folder for this URL.
        output_formats: Every format the current run requests.

    Returns:
        A mapping of each requested format to its copied path when the prior run
        held every requested format and each source file still exists on disk;
        otherwise ``None`` to tell the caller to fall through to LLM extraction.
    """
    prior_paths_raw = prior.get("file_paths")
    if not prior_paths_raw:
        return None
    prior_paths = json.loads(prior_paths_raw)

    copied: dict[OutputFormat, Path] = {}
    for fmt in output_formats:
        src_str = prior_paths.get(fmt.value)
        if not src_str:
            return None
        src = Path(src_str)
        if not src.exists():
            return None
        dst = url_output_folder / src.name
        shutil.copyfile(src, dst)
        copied[fmt] = dst
    return copied


def process_url(
    current_url: str,
    raw_html: str,
    config: ScrapeConfig,
    *,
    cb: ParAICallbackHandler,
    status: Status | None,
    llm_needed: bool,
    llm_config: LlmConfig | None,
    dynamic_model_container: type[BaseModel] | None,
) -> None:
    """Process a single fetched URL end to end.

    Covers link extraction, markdown conversion, raw save, optional LLM
    extraction, ``mark_complete``, and the per-URL error handler that classifies
    the exception, records it, and backs off the domain rate limit on
    network/timeout failures.

    Args:
        current_url: The URL being processed in this iteration.
        raw_html: The fetched HTML for ``current_url``.
        config: The fully-resolved scrape configuration.
        cb: The active par-ai-core callback handler (for cost reporting).
        status: The active Rich status spinner, or ``None`` when running inside
            the concurrent worker pool (workers must not touch the live spinner).
        llm_needed: Whether LLM extraction is enabled for this run.
        llm_config: The LLM configuration, or ``None`` when ``llm_needed`` is False.
        dynamic_model_container: The generated listings container class, or
            ``None`` when ``llm_needed`` is False.
    """
    run_name = config.run_name
    try:
        _print_locked(f"[green]{escape(current_url)}")

        url_output_folder = get_url_output_folder(config.output_folder, run_name, current_url)

        # 2. Print for debugging
        _print_locked(f"[blue]Output folder: {url_output_folder}[/blue]")
        # Create necessary directories
        if llm_needed:
            url_output_folder.mkdir(parents=True, exist_ok=True)
        else:
            url_output_folder.parent.mkdir(parents=True, exist_ok=True)

        if not raw_html:
            raise ValueError("No data was fetched")

        if (
            config.crawl_type == CrawlType.SINGLE_LEVEL and current_url == config.url
        ) or config.crawl_type == CrawlType.DOMAIN:
            # Extract links, respecting robots.txt
            page_links = extract_links(
                current_url,
                raw_html,
                config.crawl_type,
                respect_robots=config.respect_robots,
                console=console_out,
                ticket_id=run_name,
            )

            # Calculate the current page depth
            current_depth = get_url_depth(run_name, current_url)

            # Add extracted links to queue with incremented depth
            if page_links:
                _print_locked(f"[cyan]Found {len(page_links)} links on {current_url}")
                add_to_queue(run_name, page_links, current_depth + 1)
        # Detect a Next.js client-side crash before markdown conversion can
        # mangle the marker; the full sentence avoids false positives that the
        # old two-word "Application error" substring caused. Raising ScrapeError
        # routes the failure through classify_error -> mark_error.
        if NEXTJS_CLIENT_ERROR_MARKER in raw_html:
            raise ScrapeError("Next.js client-side application error page detected")

        if status is not None:
            status.update("[bold cyan]Converting HTML to Markdown...")
        markdown = html_to_markdown(raw_html, url=current_url, include_images=True)
        if not markdown:
            raise ValueError("Markdown data is empty")

        # Save raw data
        if status is not None:
            status.update("[bold cyan]Saving raw data...")
        raw_output_path = save_raw_data(markdown, url_output_folder)

        # ENH-002: hash the converted markdown, not the raw HTML. HTML carries
        # volatile noise (CSRF tokens, per-request timestamps in attributes) that
        # markdown conversion mostly strips, so the hash stays stable across
        # fetches of an unchanged page.
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()

        # Reuse a prior run's extracted outputs when the page is unchanged and
        # LLM extraction would otherwise be re-paid. find_completed_by_hash
        # excludes the current run by ticket_id so a row can never match itself.
        # If reuse is not possible (no prior match, a requested format is absent
        # from the prior run, or a prior output file was since deleted) we fall
        # through to normal LLM extraction below.
        if config.if_changed and llm_needed:
            prior = find_completed_by_hash(current_url, content_hash, run_name)
            if prior is not None:
                copied_paths = _copy_prior_outputs(prior, url_output_folder, config.output_format)
                if copied_paths is not None:
                    mark_complete(
                        run_name,
                        current_url,
                        raw_file_path=raw_output_path,
                        file_paths=copied_paths,
                        content_hash=content_hash,
                    )
                    _print_locked(f"[cyan]Unchanged since previous run — reused extraction for {escape(current_url)}")
                    return

        if llm_needed:
            if status is not None:
                status.update("[bold cyan]Extracting data with LLM...")
            if dynamic_model_container is None or llm_config is None:
                raise RuntimeError("LLM configuration is required but was not initialized")
            formatted_data = format_data(
                data=markdown,
                dynamic_listings_container=dynamic_model_container,
                llm_config=llm_config,
                prompt_cache=config.prompt_cache,
                extraction_prompt=config.extraction_prompt,
            )
            if not getattr(formatted_data, "listings", []):
                raise ValueError("No data was found by the LLM.")

            # Save formatted data
            if status is not None:
                status.update("[bold cyan]Saving extracted data...")
            _, file_paths = save_formatted_data(
                formatted_data=formatted_data,
                run_name=run_name,
                output_folder=url_output_folder,
                output_formats=config.output_format,
            )
        else:
            file_paths = {}
        if OutputFormat.MARKDOWN not in file_paths:
            file_paths[OutputFormat.MARKDOWN] = raw_output_path

        mark_complete(
            run_name,
            current_url,
            raw_file_path=raw_output_path,
            file_paths=file_paths,
            content_hash=content_hash,
        )

        # Display output if requested
        if config.display_output:
            with _console_lock:
                try:
                    output_key = OutputFormat(config.display_output.value)
                except ValueError:
                    output_key = None
                if output_key is not None and output_key in file_paths:
                    try:
                        content = file_paths[output_key].read_text(encoding="utf-8")
                        display_formatted_output(content, config.display_output, console_out)
                    except Exception as e:
                        console_out.print(f"[bold red]Error reading output file: {str(e)}[/bold red]")
                else:
                    console_out.print(f"[bold red]Invalid output type: {config.display_output.value}[/bold red]")
        if llm_needed:
            with _console_lock:
                console_out.print("Current session price:")
                show_llm_cost(cb.usage_metadata, show_pricing=PricingDisplay.PRICE, console=console_out)

        _print_locked(
            Panel.fit(
                "\n".join(set([str(p) for p in file_paths.values()] + [str(raw_output_path)])),
                title="Files",
            )
        )
    except Exception as e:
        error_type = classify_error(e)
        error_msg = str(e)

        mark_error(run_name, current_url, error_msg, error_type)
        _print_locked(
            f"[bold red]URL processing error ([yellow]{error_type.value}[/yellow]):[/bold red]"
            f"[blue]{escape(current_url)}[/blue] {escape(error_msg)}"
        )

        # Adjust rate limits on network errors
        if error_type == ErrorType.NETWORK or error_type == ErrorType.TIMEOUT:
            domain = urlparse(current_url).netloc
            new_delay = increase_crawl_delay(domain)
            _print_locked(f"[yellow]Increased rate limit for {domain} to {new_delay} seconds[/yellow]")


def run_crawl(config: ScrapeConfig) -> int:
    """Run the full crawl lifecycle described by ``config``.

    Args:
        config: The fully-resolved scrape configuration.

    Returns:
        Exit code: 0 on normal completion, 1 if a fatal error was caught by
        the outermost handler. The ``finally`` cleanup always runs before the
        code is returned.
    """
    # Set the scraper's USER_AGENT once the scraper is actually being configured
    # (ARC-012): importing the package no longer mutates the environment.
    # setdefault preserves a user-provided USER_AGENT.
    os.environ.setdefault("USER_AGENT", f"{__application_title__} {__version__}")

    llm_needed, model, llm_config, dynamic_model_container = validate_llm_options(config)
    print_config_panels(config, model, llm_needed)

    run_name = config.run_name

    exit_code = 0
    with console_out.capture() if config.silent else nullcontext():
        if config.cleanup in [CleanupType.BEFORE, CleanupType.BOTH]:
            _remove_run_output(config.output_folder, run_name)
        try:
            init_db()
            add_to_queue(run_name, [config.url])

            with get_parai_callback(show_pricing=config.pricing if llm_needed else PricingDisplay.NONE) as cb:
                with console_out.status("[bold green]Starting fetch loop...") as status:
                    start_time = time.time()
                    num_pages: int = 0
                    # Set initial crawl delay for the starting domain
                    if config.respect_rate_limits and config.crawl_delay > 1:
                        initial_domain = urlparse(config.url).netloc
                        set_crawl_delay(initial_domain, config.crawl_delay)

                    while num_pages < config.crawl_max_pages:
                        # Get queue statistics
                        queue_stats = get_queue_stats(run_name)
                        queued = queue_stats.get(PageStatus.QUEUED.value, 0)
                        completed = queue_stats.get(PageStatus.COMPLETED.value, 0)
                        errors = queue_stats.get(PageStatus.ERROR.value, 0)
                        active = queue_stats.get(PageStatus.ACTIVE.value, 0)

                        status.update(
                            f"[bold cyan]Queue status: "
                            f"[yellow]{queued}[/yellow] queued, "
                            f"[green]{completed}[/green] completed, "
                            f"[red]{errors}[/red] errors, "
                            f"[blue]{active}[/blue] active"
                        )

                        urls = get_next_urls(
                            run_name,
                            config.crawl_batch_size,
                            config.scrape_retries,
                            respect_rate_limits=config.respect_rate_limits,
                        )

                        if not urls:
                            # Check if there are any active URLs that might complete
                            if active > 0:
                                console_out.print(f"[yellow]Waiting for {active} active URLs to complete...[/yellow]")
                                time.sleep(2)  # Give a small delay to avoid tight loop
                                continue
                            else:
                                break
                        num_pages += len(urls)

                        try:
                            raw_htmls = fetch_url(
                                urls,
                                fetch_using=config.scraper.value,
                                max_parallel=config.scrape_max_parallel,
                                sleep_time=config.sleep_time,
                                wait_type=config.wait_type,
                                wait_selector=config.wait_selector,
                                headless=config.headless,
                                verbose=True,
                                console=console_out,
                            )
                            if not raw_htmls:
                                raise ValueError("No data was fetched")

                            if len(raw_htmls) != len(urls):
                                raise ValueError(f"Mismatch between URLs {len(urls)} and fetched data {len(raw_htmls)}")
                            url_data = zip(urls, raw_htmls, strict=True)
                            workers = max(1, config.scrape_max_parallel)
                            if workers == 1:
                                # Default path: identical to pre-ENH-001 behavior.
                                for current_url, raw_html in url_data:
                                    process_url(
                                        current_url,
                                        raw_html,
                                        config,
                                        cb=cb,
                                        status=status,
                                        llm_needed=llm_needed,
                                        llm_config=llm_config,
                                        dynamic_model_container=dynamic_model_container,
                                    )
                            else:
                                # ENH-001: overlap per-URL processing across the
                                # batch so LLM round-trip latency is paid
                                # concurrently. Workers never touch the live status
                                # spinner (status=None); queue writes are safe via
                                # the per-thread WAL connections (ENH-004).
                                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scrape") as pool:
                                    futures = {
                                        pool.submit(
                                            process_url,
                                            u,
                                            h,
                                            config,
                                            cb=cb,
                                            status=None,
                                            llm_needed=llm_needed,
                                            llm_config=llm_config,
                                            dynamic_model_container=dynamic_model_container,
                                        ): u
                                        for u, h in url_data
                                    }
                                    for fut in as_completed(futures):
                                        # process_url routes its own errors to
                                        # mark_error; result() surfaces only
                                        # unexpected bugs (e.g. KeyboardInterrupt).
                                        fut.result()
                        except Exception as e:
                            error_type = classify_error(e)
                            error_msg = str(e)

                            for current_url in urls:
                                mark_error(run_name, current_url, error_msg, error_type)

                            console_out.print(
                                f"[bold red]A fetch error occurred ([yellow]{error_type.value}[/yellow]):[/bold red] {error_msg}"
                            )
                    duration = time.time() - start_time
                    rate = num_pages / duration if duration > 0 else 0.0
                    console_out.print(
                        Panel.fit(f"Pages {num_pages} in {duration:.1f} seconds. {rate:.1f} pages per second.")
                    )
                    if llm_needed:
                        console_out.print("Grand total:")
        except Exception as e:
            console_out.print(f"[bold red]A general error occurred:[/bold red] {str(e)}")
            exit_code = 1
        finally:
            close_connections()
            if config.cleanup in [CleanupType.BOTH, CleanupType.AFTER]:
                with console_out.status("[bold yellow]Cleaning up..."):
                    _remove_run_output(config.output_folder, run_name)
    return exit_code
