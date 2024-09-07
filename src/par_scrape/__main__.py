"""Main entry point for par_scrape."""

import csv
import json
import os
import shutil
import asyncio
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import List, Optional, Annotated
from enum import Enum
from uuid import uuid4
from contextlib import nullcontext
from asyncio import run as aiorun
import aiofiles
import aiofiles.os as aos

import typer
from dotenv import load_dotenv
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from par_scrape.scrape_data import (
    save_raw_data,
    create_dynamic_listing_model,
    create_listings_container_model,
    format_data,
    save_formatted_data,
)
from par_scrape.fetch_html import (
    fetch_html_selenium,
    fetch_html_playwright,
    html_to_markdown_with_readability,
)
from par_scrape.pricing import display_price_summary
from par_scrape.utils import console
from par_scrape import __version__, __application_title__
from par_scrape.lib.llm_providers import (
    LlmProvider,
    provider_default_models,
    provider_env_key_names,
)

# Load the .env file from the project folder
load_dotenv(dotenv_path=".env")
# Load the .env file from the users home folder
load_dotenv(dotenv_path=Path("~/.par-scrape.env").expanduser())

# Initialize Typer app
app = typer.Typer(help="Web scraping tool with options for Selenium or Playwright")


class CleanupType(str, Enum):
    """Enum for cleanup choices."""

    NONE = "none"
    BEFORE = "before"
    AFTER = "after"
    BOTH = "both"


class DisplayOutputFormat(str, Enum):
    """Enum for display output format choices."""

    MD = "md"
    CSV = "csv"
    JSON = "json"


class ScraperChoice(str, Enum):
    """Enum for scraper choices."""

    SELENIUM = "selenium"
    PLAYWRIGHT = "playwright"


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        print(f"{__application_title__}: {__version__}")
        raise typer.Exit()


# pylint: disable=too-many-statements,dangerous-default-value,too-many-arguments, too-many-locals
@app.command()
def main(
    url: Annotated[
        str, typer.Option("--url", "-u", help="URL to scrape", prompt=True)
    ] = "https://openai.com/api/pricing/",
    fields: Annotated[
        List[str],
        typer.Option(
            "--fields", "-f", help="Fields to extract from the webpage", prompt=True
        ),
    ] = [
        "Model",
        "Pricing Input",
        "Pricing Output",
    ],
    scraper: Annotated[
        ScraperChoice,
        typer.Option(
            "--scraper",
            "-s",
            help="Scraper to use: 'selenium' or 'playwright'",
            case_sensitive=False,
        ),
    ] = ScraperChoice.SELENIUM,
    headless: Annotated[
        bool,
        typer.Option("--headless", "-h", help="Run in headless mode (for Selenium)"),
    ] = False,
    sleep_time: Annotated[
        int,
        typer.Option(
            "--sleep-time", "-t", help="Time to sleep before scrolling (in seconds)"
        ),
    ] = 5,
    pause: Annotated[
        bool,
        typer.Option(
            "--pause", "-p", help="Wait for user input before closing browser"
        ),
    ] = False,
    ai_provider: Annotated[
        LlmProvider,
        typer.Option("--ai-provider", "-a", help="AI provider to use for processing"),
    ] = LlmProvider.OPENAI,
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model",
            "-m",
            help="AI model to use for processing. If not specified, a default model will be used.",
        ),
    ] = None,
    display_output: Annotated[
        Optional[DisplayOutputFormat],
        typer.Option(
            "--display-output",
            "-d",
            help="Display output in terminal (md, csv, or json)",
        ),
    ] = None,
    output_folder: Annotated[
        Path,
        typer.Option(
            "--output-folder", "-o", help="Specify the location of the output folder"
        ),
    ] = Path("./output"),
    silent: Annotated[
        bool,
        typer.Option("--silent", "-q", help="Run in silent mode, suppressing output"),
    ] = False,
    run_name: Annotated[
        str,
        typer.Option("--run-name", "-n", help="Specify a name for this run"),
    ] = "",
    version: Annotated[  # pylint: disable=unused-argument
        Optional[bool],
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = None,
    pricing: Annotated[
        bool,
        typer.Option("--pricing", help="Enable pricing summary display"),
    ] = False,
    cleanup: Annotated[
        CleanupType,
        typer.Option("--cleanup", "-c", help="How to handle cleanup of output folder."),
    ] = CleanupType.NONE,
):
    """Scrape and analyze data from a website."""
    if not model:
        model = provider_default_models[ai_provider]

    async def _main():  # pylint: disable=too-many-locals, too-many-branches, too-many-statements
        """Scrape and analyze data from a website."""
        nonlocal run_name
        if ai_provider != LlmProvider.OLLAMA:
            key_name = provider_env_key_names[ai_provider]
            if not os.environ.get(key_name):
                console.print(
                    f"[bold red]{key_name} environment variable not set. Exiting...[/bold red]"
                )
                raise typer.Exit(1)
        with console.capture() if silent else nullcontext():
            if cleanup in [CleanupType.BEFORE, CleanupType.BOTH]:
                if await aos.path.exists(output_folder):
                    shutil.rmtree(output_folder)
                    console.print(
                        f"[bold green]Removed existing output folder: {output_folder}[/bold green]"
                    )
            try:
                # Generate run_name if not provided
                if not run_name:
                    run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
                else:
                    # Ensure run_name is filesystem-friendly
                    run_name = "".join(
                        c for c in run_name if c.isalnum() or c in ("-", "_")
                    )
                    if not run_name:
                        run_name = str(uuid4())

                # Display summary of options
                console.print(
                    Panel.fit(
                        Text.assemble(
                            ("URL: ", "cyan"),
                            (f"{url}", "green"),
                            "\n",
                            ("AI Provider: ", "cyan"),
                            (f"{ai_provider.value}", "green"),
                            "\n",
                            ("Model: ", "cyan"),
                            (f"{model}", "green"),
                            "\n",
                            ("Scraper: ", "cyan"),
                            (f"{scraper}", "green"),
                            "\n",
                            ("Headless: ", "cyan"),
                            (f"{headless}", "green"),
                            "\n",
                            ("Sleep Time: ", "cyan"),
                            (f"{sleep_time} seconds", "green"),
                            "\n",
                            ("Pause: ", "cyan"),
                            (f"{pause}", "green"),
                            "\n",
                            ("Fields to extract: ", "cyan"),
                            (", ".join(fields), "green"),
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

                with console.status(
                    "[bold green]Working on data extraction and processing..."
                ) as status:
                    # Scrape data
                    status.update("[bold cyan]Fetching HTML...")
                    if scraper == ScraperChoice.PLAYWRIGHT:
                        raw_html = await fetch_html_playwright(url, sleep_time, pause)
                    else:
                        raw_html = await fetch_html_selenium(
                            url, headless, sleep_time, pause
                        )

                    status.update("[bold cyan]Converting HTML to Markdown...")
                    markdown = await html_to_markdown_with_readability(raw_html)

                    # Save raw data
                    status.update("[bold cyan]Saving raw data...")
                    await save_raw_data(markdown, run_name, output_folder)

                    # Create the dynamic listing model
                    status.update("[bold cyan]Creating dynamic models...")
                    dynamic_listing_model = create_dynamic_listing_model(fields)
                    dynamic_listings_container = create_listings_container_model(
                        dynamic_listing_model
                    )

                    # Format data
                    status.update("[bold cyan]Formatting data...")
                    formatted_data = await format_data(
                        markdown, dynamic_listings_container, model, ai_provider
                    )

                    # Save formatted data
                    status.update("[bold cyan]Saving formatted data...")
                    _, file_paths = await save_formatted_data(
                        formatted_data, run_name, output_folder
                    )

                    # Convert formatted_data back to text for token counting
                    formatted_data_text = json.dumps(formatted_data.model_dump())

                # Display output if requested
                if display_output:
                    if display_output.value in file_paths:
                        async with aiofiles.open(
                            file_paths[display_output.value], "rt", encoding="utf-8"
                        ) as f:
                            content = await f.read()
                        if display_output == DisplayOutputFormat.MD:
                            console.print(Markdown(content))
                        elif display_output == DisplayOutputFormat.CSV:
                            # Convert CSV to rich Table
                            table = Table(title="CSV Data")
                            csv_reader = csv.reader(StringIO(content))
                            headers = next(csv_reader)
                            for header in headers:
                                table.add_column(header, style="cyan")
                            for row in csv_reader:
                                table.add_row(*row)
                            console.print(table)
                        elif display_output == DisplayOutputFormat.JSON:
                            console.print(Syntax(content, "json"))
                    else:
                        console.print(
                            f"[bold red]Invalid output type: {display_output.value}[/bold red]"
                        )

                if pricing:
                    await display_price_summary(
                        status, model, markdown, formatted_data_text
                    )

            except Exception as e:  # pylint: disable=broad-except
                print(e)
                console.print(f"[bold red]An error occurred:[/bold red] {str(e)}")

            finally:
                if cleanup in [CleanupType.BOTH, CleanupType.AFTER]:
                    with console.status("[bold yellow]Cleaning up..."):
                        if await aos.path.exists(output_folder):
                            await asyncio.to_thread(shutil.rmtree, output_folder)
                            console.print(
                                f"[bold green]Removed output folder and its contents: {output_folder}[/bold green]"
                            )

    aiorun(_main())


if __name__ == "__main__":
    app()
