"""Main entry point for par_scrape."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from dotenv import load_dotenv
from par_ai_core.llm_config import ReasoningEffort
from par_ai_core.llm_providers import LlmProvider
from par_ai_core.output_utils import DisplayOutputFormat
from par_ai_core.par_logging import console_out
from par_ai_core.pricing_lookup import PricingDisplay
from par_ai_core.web_tools import ScraperChoice, ScraperWaitType

from par_scrape import __application_title__, __version__
from par_scrape.crawl import CrawlType
from par_scrape.enums import CleanupType, OutputFormat
from par_scrape.runner import ScrapeConfig, run_crawl

# Initialize Typer app
app = typer.Typer(help="Web scraping tool with options for Selenium or Playwright")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console_out.print(f"{__application_title__}: {__version__}")
        raise typer.Exit()


def _startup() -> None:
    """Run one-time startup side effects (ARC-012).

    Migrates the legacy ``~/.par-scrape.env`` file to ``~/.par_scrape.env`` and
    loads the home dotenv. Lives in a function so that merely importing the
    module (e.g. ``--version`` or test collection) no longer mutates the user's
    home directory or process environment. Must run before provider env vars
    are read and before the SEC-002 ``--env-file`` handling so load order stays
    home-file-first then explicit-file.
    """
    old_env_path = Path("~/.par-scrape.env").expanduser()
    new_env_path = Path("~/.par_scrape.env").expanduser()

    if old_env_path.exists():
        if new_env_path.exists():
            old_env_path.unlink()
        else:
            console_out.print(f"[bold yellow]Renaming {old_env_path} to {new_env_path}")
            old_env_path.rename(new_env_path)

    # Load the .env file from the users home folder
    load_dotenv(dotenv_path=new_env_path)


@app.command()
def main(
    url: Annotated[str, typer.Option("--url", "-u", help="URL to scrape")],
    output_format: Annotated[
        list[OutputFormat] | None,
        typer.Option("--output-format", "-O", help="Output format for the scraped data", show_default="md"),
    ] = None,
    fields: Annotated[
        list[str] | None,
        typer.Option(
            "--fields",
            "-f",
            help="Fields to extract from the webpage",
            show_default="Model, Pricing Input, Pricing Output, Cache Price",
        ),
    ] = None,
    scraper: Annotated[
        ScraperChoice,
        typer.Option(
            "--scraper",
            "-s",
            help="Scraper to use: 'selenium' or 'playwright'",
            case_sensitive=False,
        ),
    ] = ScraperChoice.PLAYWRIGHT,
    scrape_retries: Annotated[
        int,
        typer.Option("--retries", "-r", help="Retry attempts for failed scrapes"),
    ] = 3,
    scrape_max_parallel: Annotated[
        int,
        typer.Option("--scrape-max-parallel", "-P", help="Max parallel fetch and extraction workers"),
    ] = 1,
    wait_type: Annotated[
        ScraperWaitType,
        typer.Option(
            "--wait-type",
            "-w",
            help="Method to use for page content load waiting",
            case_sensitive=False,
        ),
    ] = ScraperWaitType.SLEEP,
    wait_selector: Annotated[
        str | None,
        typer.Option(
            "--wait-selector",
            "-i",
            help="Selector or text to use for page content load waiting.",
        ),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option("--headless", "-h", help="Run in headless mode (for Selenium)"),
    ] = False,
    sleep_time: Annotated[
        int,
        typer.Option("--sleep-time", "-t", help="Time to sleep before scrolling (in seconds)"),
    ] = 2,
    ai_provider: Annotated[
        LlmProvider,
        typer.Option("--ai-provider", "-a", help="AI provider to use for processing"),
    ] = LlmProvider.OPENAI,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="AI model to use for processing. If not specified, a default model will be used.",
        ),
    ] = None,
    ai_base_url: Annotated[
        str | None,
        typer.Option(
            "--ai-base-url",
            "-b",
            help="Override the base URL for the AI provider.",
        ),
    ] = None,
    prompt_cache: Annotated[
        bool,
        typer.Option("--prompt-cache", help="Enable prompt cache for Anthropic provider"),
    ] = False,
    reasoning_effort: Annotated[
        ReasoningEffort | None,
        typer.Option(
            "--reasoning-effort",
            help="Reasoning effort level to use for o1 and o3 models.",
        ),
    ] = None,
    reasoning_budget: Annotated[
        int | None,
        typer.Option(
            "--reasoning-budget",
            help="Maximum context size for reasoning.",
        ),
    ] = None,
    display_output: Annotated[
        DisplayOutputFormat | None,
        typer.Option(
            "--display-output",
            "-d",
            help="Display output in terminal (md, csv, or json)",
        ),
    ] = None,
    output_folder: Annotated[
        Path,
        typer.Option("--output-folder", "-o", help="Specify the location of the output folder"),
    ] = Path("./output"),
    silent: Annotated[
        bool,
        typer.Option("--silent", "-q", help="Run in silent mode, suppressing output"),
    ] = False,
    run_name: Annotated[
        str,
        typer.Option(
            "--run-name",
            "-n",
            help="Specify a name for this run. Can be used to resume a crawl Defaults to YYYYmmdd_HHMMSS",
        ),
    ] = "",
    pricing: Annotated[
        PricingDisplay,
        typer.Option("--pricing", "-p", help="Enable pricing summary display"),
    ] = PricingDisplay.DETAILS,
    cleanup: Annotated[
        CleanupType,
        typer.Option("--cleanup", "-c", help="How to handle cleanup of output folder"),
    ] = CleanupType.NONE,
    extraction_prompt: Annotated[
        Path | None,
        typer.Option("--extraction-prompt", "-e", help="Path to the extraction prompt file"),
    ] = None,
    if_changed: Annotated[
        bool,
        typer.Option(
            "--if-changed",
            help="Skip LLM extraction for pages unchanged since a previous completed run "
            "(matched by content hash); reuses that run's extracted outputs.",
        ),
    ] = False,
    crawl_type: Annotated[
        CrawlType,
        typer.Option(
            "--crawl-type",
            "-C",
            help="Enable crawling mode",
            case_sensitive=False,
        ),
    ] = CrawlType.SINGLE_PAGE,
    crawl_max_pages: Annotated[
        int,
        typer.Option("--crawl-max-pages", "-M", help="Maximum number of pages to crawl this session"),
    ] = 100,
    crawl_batch_size: Annotated[
        int,
        typer.Option("--crawl-batch-size", "-B", help="Maximum number of pages to load from the queue at once"),
    ] = 1,
    respect_rate_limits: Annotated[
        bool,
        typer.Option("--respect-rate-limits", help="Whether to use domain-specific rate limiting"),
    ] = True,
    respect_robots: Annotated[
        bool,
        typer.Option("--respect-robots", help="Whether to respect robots.txt"),
    ] = False,
    crawl_delay: Annotated[
        int,
        typer.Option("--crawl-delay", help="Default delay in seconds between requests to the same domain"),
    ] = 1,
    env_file: Annotated[
        Path | None,
        typer.Option(
            "--env-file",
            help="Load environment variables from this file. Values already set in the "
            "environment or ~/.par_scrape.env take precedence.",
        ),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = None,
):
    """
    Scrape and optionally crawl / extract data from a website.

    AI is only used if an output format other than md is specified.

    Crawl types:

    - single_page: Only scrape the specified URL.

    - single_level: Scrape the specified URL and all links on that page that have the same host.

    - domain: Scrape the specified URL and all links and their pages on that page that have the same host.
    """

    _startup()

    if env_file:
        if not env_file.exists():
            console_out.print(f"[bold red]Env file not found: {env_file}[/bold red]")
            raise typer.Exit(code=1)
        load_dotenv(dotenv_path=env_file)

    output_format = output_format or [OutputFormat.MARKDOWN]
    fields = fields or ["Model", "Pricing Input", "Pricing Output", "Cache Price"]

    if display_output and display_output not in output_format:
        console_out.print(
            f"[bold red]Display output format '{display_output}' is not in the specified output formats.[/bold red]"
        )
        raise typer.Exit(1)

    # Generate run_name if not provided
    if not run_name:
        run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    else:
        # Ensure run_name is filesystem-friendly
        run_name = "".join(c for c in run_name if c.isalnum() or c in ("-", "_"))
        if not run_name:
            run_name = str(uuid4())

    url = url.rstrip("/")

    config = ScrapeConfig(
        url=url,
        output_format=output_format,
        fields=fields,
        scraper=scraper,
        scrape_retries=scrape_retries,
        scrape_max_parallel=scrape_max_parallel,
        run_name=run_name,
        output_folder=output_folder,
        cleanup=cleanup,
        crawl_type=crawl_type,
        crawl_batch_size=crawl_batch_size,
        crawl_max_pages=crawl_max_pages,
        respect_robots=respect_robots,
        respect_rate_limits=respect_rate_limits,
        crawl_delay=crawl_delay,
        wait_type=wait_type,
        wait_selector=wait_selector,
        headless=headless,
        sleep_time=sleep_time,
        ai_provider=ai_provider,
        model=model,
        ai_base_url=ai_base_url,
        prompt_cache=prompt_cache,
        reasoning_effort=reasoning_effort,
        reasoning_budget=reasoning_budget,
        display_output=display_output,
        silent=silent,
        pricing=pricing,
        extraction_prompt=extraction_prompt,
        if_changed=if_changed,
    )

    code = run_crawl(config)
    if code:
        raise typer.Exit(code=code)


if __name__ == "__main__":
    app()
