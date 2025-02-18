"""Main entry point for par_scrape."""

import os
import shutil
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from dotenv import load_dotenv
from par_ai_core.llm_config import LlmConfig
from par_ai_core.llm_providers import (
    LlmProvider,
    provider_default_models,
    provider_env_key_names,
)
from par_ai_core.output_utils import DisplayOutputFormat, display_formatted_output
from par_ai_core.par_logging import console_out
from par_ai_core.pricing_lookup import PricingDisplay, show_llm_cost
from par_ai_core.provider_cb_info import get_parai_callback
from par_ai_core.web_tools import ScraperChoice, ScraperWaitType, fetch_url, html_to_markdown
from rich.panel import Panel
from rich.text import Text

from par_scrape import __application_title__, __version__
from par_scrape.crawl import (
    CrawlType,
    add_to_queue,
    extract_links,
    get_next_urls,
    get_queue_size,
    get_url_output_folder,
    init_db,
    mark_complete,
    mark_error,
)
from par_scrape.enums import CleanupType, OutputFormat
from par_scrape.scrape_data import (
    create_container_model,
    create_dynamic_model,
    format_data,
    save_formatted_data,
    save_raw_data,
)

old_env_path = Path("~/.par-scrape.env").expanduser()
new_env_path = Path("~/.par_scrape.env").expanduser()

if old_env_path.exists():
    if new_env_path.exists():
        old_env_path.unlink()
    else:
        console_out.print(f"[bold yellow]Renaming {old_env_path} to {new_env_path}")
        old_env_path.rename(new_env_path)

# Load the .env file from the project folder
load_dotenv(dotenv_path=".env")
# Load the new .env file from the users home folder
load_dotenv(dotenv_path=new_env_path)

# Initialize Typer app
app = typer.Typer(help="Web scraping tool with options for Selenium or Playwright")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        print(f"{__application_title__}: {__version__}")
        raise typer.Exit()


@app.command()
def main(
    url: Annotated[str, typer.Option("--url", "-u", help="URL to scrape")] = "https://openai.com/api/pricing/",
    output_format: Annotated[
        list[OutputFormat],
        typer.Option("--output-format", "-O", help="Output format for the scraped data"),
    ] = [OutputFormat.MARKDOWN],
    fields: Annotated[
        list[str],
        typer.Option("--fields", "-f", help="Fields to extract from the webpage"),
    ] = ["Model", "Pricing Input", "Pricing Output", "Cache Price"],
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
        typer.Option("--scrape-max-parallel", "-P", help="Max parallel fetch requests"),
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
        typer.Option("--cleanup", "-c", help="How to handle cleanup of output folder."),
    ] = CleanupType.NONE,
    extraction_prompt: Annotated[
        Path | None,
        typer.Option("--extraction-prompt", "-e", help="Path to the extraction prompt file"),
    ] = None,
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
        typer.Option("--crawl-batch-size", "-b", help="Maximum number of pages to load from the queue at once"),
    ] = 1,
    version: Annotated[  # pylint: disable=unused-argument
        bool | None,
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = None,
):
    """
    Scrape and optionally crawl / extract data from a website.

    AI is only used if an output format other than md is specified.

    Crawl types:

    - single_page: Only scrape the specified URL.

    - single_level: Scrape the specified URL and all links on that page that are have the same top level domain.

    - domain: Scrape the specified URL and all links and their pages on that page that are have the same domain.
    """

    if display_output and display_output not in output_format:
        console_out.print(
            f"[bold red]Display output format '{display_output}' is not in the specified output formats.[/bold red]"
        )
        raise typer.Exit(1)

    outputs_needing_llm = [OutputFormat.JSON, OutputFormat.CSV, OutputFormat.EXCEL]
    llm_needed = any(format in output_format for format in outputs_needing_llm)
    if llm_needed:
        if not model:
            model = provider_default_models[ai_provider]

        if ai_provider not in [LlmProvider.OLLAMA, LlmProvider.BEDROCK, LlmProvider.LITELLM]:
            key_name = provider_env_key_names[ai_provider]
            if not os.environ.get(key_name):
                console_out.print(f"[bold red]{key_name} environment variable not set. Exiting...[/bold red]")
                raise typer.Exit(1)

        if prompt_cache and ai_provider != LlmProvider.ANTHROPIC:
            console_out.print(
                "[bold red]Prompt cache flag is only available for Anthropic provider. Exiting...[/bold red]"
            )
            raise typer.Exit(1)

        console_out.print("[bold cyan]Creating llm config and dynamic models...")
        llm_config = LlmConfig(provider=ai_provider, model_name=model, temperature=0, base_url=ai_base_url)
        dynamic_extraction_model = create_dynamic_model(fields)
        dynamic_model_container = create_container_model(dynamic_extraction_model)

        console_out.print(
            Panel.fit(
                Text.assemble(
                    ("AI Provider: ", "cyan"),
                    (f"{ai_provider.value}", "green"),
                    "\n",
                    ("Model: ", "cyan"),
                    (f"{model}", "green"),
                    "\n",
                    ("AI Provider Base URL: ", "cyan"),
                    (f"{ai_base_url or 'default'}", "green"),
                    "\n",
                    ("Prompt Cache: ", "cyan"),
                    (f"{prompt_cache}", "green"),
                    "\n",
                    ("Fields to extract: ", "cyan"),
                    (", ".join(fields), "green"),
                    "\n",
                    ("Pricing Display: ", "cyan"),
                    (f"{pricing.value}", "green"),
                ),
                title="[bold]AI Configuration",
                border_style="bold",
            )
        )
    else:
        llm_config = None
        dynamic_model_container = None

    # Generate run_name if not provided
    if not run_name:
        run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    else:
        # Ensure run_name is filesystem-friendly
        run_name = "".join(c for c in run_name if c.isalnum() or c in ("-", "_"))
        if not run_name:
            run_name = str(uuid4())

    url = url.rstrip("/")
    console_out.print(
        Panel.fit(
            Text.assemble(
                ("Primary URL: ", "cyan"),
                (f"{url}", "green"),
                "\n",
                ("Scraper: ", "cyan"),
                (f"{scraper}", "green"),
                "\n",
                ("Scrape Max Parallel: ", "cyan"),
                (f"{scrape_max_parallel}", "green"),
                "\n",
                ("Retries: ", "cyan"),
                (
                    f"{scrape_retries}",
                    "green",
                ),
                "\n",
                ("Crawl Type: ", "cyan"),
                (f"{crawl_type.value}", "green"),
                "\n",
                ("Crawl Batch Size: ", "cyan"),
                (f"{crawl_batch_size}", "green"),
                "\n",
                ("Output Format: ", "cyan"),
                (", ".join([f"{format.value}" for format in output_format]), "green"),
                "\n",
                ("Max Pages: ", "cyan"),
                (f"{crawl_max_pages}", "green"),
                "\n",
                ("Headless: ", "cyan"),
                (f"{headless}", "green"),
                "\n",
                ("Wait Type: ", "cyan"),
                (f"{wait_type.value}", "green"),
                "\n",
                ("Wait Selector: ", "cyan"),
                (
                    f"{wait_selector if wait_type in (ScraperWaitType.SELECTOR, ScraperWaitType.TEXT) else 'N/A'}",
                    "green",
                ),
                "\n",
                ("Sleep Time: ", "cyan"),
                (
                    f"{sleep_time} seconds",
                    "green",
                ),
                "\n",
                ("Display output: ", "cyan"),
                (f"{display_output or 'None'}", "green"),
                "\n",
                ("Silent mode: ", "cyan"),
                (f"{silent}", "green"),
                "\n",
                ("Cleanup: ", "cyan"),
                (f"{cleanup}", "green"),
            ),
            title="[bold]Scraping Configuration",
            border_style="bold",
        )
    )

    with console_out.capture() if silent else nullcontext():
        if cleanup in [CleanupType.BEFORE, CleanupType.BOTH]:
            if os.path.exists(output_folder):
                shutil.rmtree(output_folder)
                console_out.print(f"[bold green]Removed existing output folder: {output_folder}[/bold green]")
        try:
            init_db()
            add_to_queue(run_name, [url])

            with get_parai_callback(show_pricing=pricing if llm_needed else PricingDisplay.NONE) as cb:
                with console_out.status("[bold green]Starting fetch loop...") as status:
                    start_time = time.time()
                    num_pages: int = 0
                    while num_pages < crawl_max_pages:
                        urls = get_next_urls(run_name, crawl_batch_size, scrape_retries)
                        status.update(f"[bold cyan]URLs remaining: [yellow]{get_queue_size(run_name)}")

                        if not urls:
                            break
                        num_pages += len(urls)

                        try:
                            raw_htmls = fetch_url(
                                urls,
                                fetch_using=scraper.value,
                                max_parallel=scrape_max_parallel,
                                sleep_time=sleep_time,
                                wait_type=wait_type,
                                wait_selector=wait_selector,
                                headless=headless,
                                verbose=True,
                                console=console_out,
                            )
                            if not raw_htmls:
                                raise ValueError("No data was fetched")

                            if len(raw_htmls) != len(urls):
                                raise ValueError(f"Mismatch between URLs {len(urls)} and fetched data {len(raw_htmls)}")
                            url_data = zip(urls, raw_htmls)
                            for current_url, raw_html in url_data:
                                try:
                                    console_out.print(f"[green]{current_url}")

                                    output_folder = get_url_output_folder(output_folder, run_name, current_url)
                                    if llm_needed:
                                        output_folder.mkdir(parents=True, exist_ok=True)
                                    else:
                                        output_folder.parent.mkdir(parents=True, exist_ok=True)
                                    # console_out.print(f"[green]{output_folder}")

                                    if not raw_html:
                                        raise ValueError("No data was fetched")

                                    # console_out.print(f"cu:{current_url} -- u:{url}")

                                    if (
                                        crawl_type == CrawlType.SINGLE_LEVEL and current_url == url
                                    ) or crawl_type == CrawlType.DOMAIN:
                                        page_links = extract_links(current_url, raw_html, crawl_type)
                                        add_to_queue(run_name, page_links)
                                    # break
                                    status.update("[bold cyan]Converting HTML to Markdown...")
                                    markdown = html_to_markdown(raw_html, url=current_url, include_images=True)
                                    if not markdown:
                                        raise ValueError("Markdown data is empty")

                                    # Save raw data
                                    status.update("[bold cyan]Saving raw data...")
                                    raw_output_path = save_raw_data(markdown, output_folder)

                                    if "Application error" in markdown:
                                        raise ValueError("Application error encountered.")

                                    if llm_needed:
                                        status.update("[bold cyan]Extracting data with LLM...")
                                        assert dynamic_model_container and llm_config
                                        formatted_data = format_data(
                                            data=markdown,
                                            dynamic_listings_container=dynamic_model_container,
                                            llm_config=llm_config,
                                            prompt_cache=prompt_cache,
                                            extraction_prompt=extraction_prompt,
                                        )
                                        if not formatted_data:
                                            raise ValueError("No data was found by the LLM.")

                                        # Save formatted data
                                        status.update("[bold cyan]Saving extracted data...")
                                        _, file_paths = save_formatted_data(
                                            formatted_data=formatted_data,
                                            run_name=run_name,
                                            output_folder=output_folder,
                                            output_formats=output_format,
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
                                    )

                                    # Display output if requested
                                    if display_output:
                                        if display_output.value in file_paths:
                                            content = file_paths[display_output.value].read_text()
                                            display_formatted_output(content, display_output, console_out)
                                        else:
                                            console_out.print(
                                                f"[bold red]Invalid output type: {display_output.value}[/bold red]"
                                            )
                                    if llm_needed:
                                        console_out.print("Current session price:")
                                        show_llm_cost(
                                            cb.usage_metadata, show_pricing=PricingDisplay.PRICE, console=console_out
                                        )

                                    console_out.print(
                                        Panel.fit(
                                            "\n".join([str(p) for p in file_paths.values()] + [str(raw_output_path)]),
                                            title="Files",
                                        )
                                    )
                                except Exception as e:
                                    mark_error(run_name, current_url, str(e))
                                    console_out.print(
                                        f"[bold red]URL processing error:[/bold red][blue]{current_url}[/blue] {str(e)}"
                                    )
                        except Exception as e:
                            mark_error(run_name, current_url, str(e))
                            console_out.print(f"[bold red]A fetch error occurred:[/bold red] {str(e)}")
                    # end while num_pages < crawl_max_pages
                    duration = time.time() - start_time
                    console_out.print(
                        Panel.fit(
                            f"Pages {num_pages} in {duration:.1f} seconds. {num_pages / duration:.1f} pages per second."
                        )
                    )
                    if llm_needed:
                        console_out.print("Grand total:")

                # end queue_status
            # end get_parai_callback
        except Exception as e:
            console_out.print(f"[bold red]An general error occurred:[/bold red] {str(e)}")
        finally:
            if cleanup in [CleanupType.BOTH, CleanupType.AFTER]:
                with console_out.status("[bold yellow]Cleaning up..."):
                    if os.path.exists(output_folder):
                        shutil.rmtree(output_folder)
                        console_out.print(
                            f"[bold green]Removed output folder and its contents: {output_folder}[/bold green]"
                        )


if __name__ == "__main__":
    app()
