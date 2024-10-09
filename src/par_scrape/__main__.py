"""Main entry point for par_scrape."""

import csv
import json
import os
import shutil
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import List, Optional, Annotated
from uuid import uuid4
from contextlib import nullcontext

import typer
from dotenv import load_dotenv
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from par_scrape.enums import CleanupType, DisplayOutputFormat, ScraperChoice, WaitType
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

new_env_path = Path("~/.par_scrape.env").expanduser()
old_env_path = Path("~/.par-scrape.env").expanduser()
if old_env_path.exists():
    if new_env_path.exists():
        old_env_path.unlink()
    else:
        console.print(f"[bold yellow]Renaming {old_env_path} to {new_env_path}")
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


# pylint: disable=too-many-statements,dangerous-default-value,too-many-arguments, too-many-locals, too-many-positional-arguments, too-many-branches
@app.command()
def main(
    url: Annotated[
        str, typer.Option("--url", "-u", help="URL to scrape")
    ] = "https://openai.com/api/pricing/",
    fields: Annotated[
        List[str],
        typer.Option("--fields", "-f", help="Fields to extract from the webpage"),
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
    ] = ScraperChoice.PLAYWRIGHT,
    wait_type: Annotated[
        WaitType,
        typer.Option(
            "--wait-type",
            "-w",
            help="Method to use for page content load waiting",
            case_sensitive=False,
        ),
    ] = WaitType.SLEEP,
    wait_selector: Annotated[
        Optional[str],
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
        typer.Option(
            "--sleep-time", "-t", help="Time to sleep before scrolling (in seconds)"
        ),
    ] = 3,
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
    ai_base_url: Annotated[
        Optional[str],
        typer.Option(
            "--ai-base-url",
            "-b",
            help="Override the base URL for the AI provider.",
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
    extraction_prompt: Annotated[
        Optional[Path],
        typer.Option(
            "--extraction-prompt", "-e", help="Path to the extraction prompt file"
        ),
    ] = None,
):
    """Scrape and analyze data from a website."""
    if not model:
        model = provider_default_models[ai_provider]

    if ai_provider != LlmProvider.OLLAMA:
        key_name = provider_env_key_names[ai_provider]
        if not os.environ.get(key_name):
            console.print(
                f"[bold red]{key_name} environment variable not set. Exiting...[/bold red]"
            )
            raise typer.Exit(1)
    with console.capture() if silent else nullcontext():
        if cleanup in [CleanupType.BEFORE, CleanupType.BOTH]:
            if os.path.exists(output_folder):
                shutil.rmtree(output_folder)
                console.print(
                    f"[bold green]Removed existing output folder: {output_folder}[/bold green]"
                )

        start_time = time.time()

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

            # Check if url is a local file
            is_local_file = os.path.isfile(url)
            source_type = "Local File" if is_local_file else "URL"

            # Display summary of options
            console.print(
                Panel.fit(
                    Text.assemble(
                        (f"{source_type}: ", "cyan"),
                        (f"{url}", "green"),
                        "\n",
                        ("AI Provider: ", "cyan"),
                        (f"{ai_provider.value}", "green"),
                        "\n",
                        ("Model: ", "cyan"),
                        (f"{model}", "green"),
                        "\n",
                        ("AI Provider Base URL: ", "cyan"),
                        (f"{ai_base_url or 'default'}", "green"),
                        "\n",
                        ("Scraper: ", "cyan"),
                        (f"{scraper if not is_local_file else 'N/A'}", "green"),
                        "\n",
                        ("Headless: ", "cyan"),
                        (f"{headless if not is_local_file else 'N/A'}", "green"),
                        "\n",
                        ("Wait Type: ", "cyan"),
                        (f"{wait_type.value}", "green"),
                        "\n",
                        ("Wait Selector: ", "cyan"),
                        (
                            f"{wait_selector if wait_type in (WaitType.SELECTOR, WaitType.TEXT) else 'N/A'}",
                            "green",
                        ),
                        "\n",
                        ("Sleep Time: ", "cyan"),
                        (
                            f"{sleep_time if not is_local_file else 'N/A'} seconds",
                            "green",
                        ),
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
                if is_local_file:
                    # Read local file
                    status.update("[bold cyan]Reading local file...")
                    with open(url, "rt", encoding="utf-8") as file:
                        markdown = file.read()
                    run_name = os.path.splitext(os.path.basename(url))[0].replace(
                        "rawData_", ""
                    )
                else:
                    # Scrape data
                    status.update("[bold cyan]Fetching HTML...")
                    if scraper == ScraperChoice.PLAYWRIGHT:
                        raw_html = fetch_html_playwright(
                            url, headless, wait_type, wait_selector, sleep_time
                        )
                    else:
                        raw_html = fetch_html_selenium(
                            url, headless, wait_type, wait_selector, sleep_time
                        )

                    status.update("[bold cyan]Converting HTML to Markdown...")
                    markdown = html_to_markdown_with_readability(raw_html)
                    # Save raw data
                    status.update("[bold cyan]Saving raw data...")
                    save_raw_data(markdown, run_name, output_folder)

                # Create the dynamic listing model
                status.update("[bold cyan]Creating dynamic models...")
                dynamic_listing_model = create_dynamic_listing_model(fields)
                dynamic_listings_container = create_listings_container_model(
                    dynamic_listing_model
                )

                # Format data
                status.update("[bold cyan]Formatting data...")
                formatted_data = format_data(
                    markdown,
                    dynamic_listings_container,
                    model,
                    ai_provider,
                    extraction_prompt,
                    ai_base_url,
                )
                if not formatted_data:
                    raise ValueError("No data was found by the scrape.")

                # Save formatted data
                status.update("[bold cyan]Saving formatted data...")
                _, file_paths = save_formatted_data(
                    formatted_data, run_name, output_folder
                )

                # Convert formatted_data back to text for token counting
                formatted_data_text = json.dumps(formatted_data.model_dump())

            # Display output if requested
            if display_output:
                if display_output.value in file_paths:
                    with open(
                        file_paths[display_output.value], "rt", encoding="utf-8"
                    ) as f:
                        content = f.read()
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

            duration = time.time() - start_time
            console.print(Panel.fit(f"Done in {duration:.2f} seconds."))
            # Display price summary
            if pricing:
                display_price_summary(status, model, markdown, formatted_data_text)

        except Exception as e:  # pylint: disable=broad-except
            # print(e)
            console.print(f"[bold red]An error occurred:[/bold red] {str(e)}")

        finally:
            if cleanup in [CleanupType.BOTH, CleanupType.AFTER]:
                with console.status("[bold yellow]Cleaning up..."):
                    if os.path.exists(output_folder):
                        shutil.rmtree(output_folder)
                        console.print(
                            f"[bold green]Removed output folder and its contents: {output_folder}[/bold green]"
                        )


if __name__ == "__main__":
    app()
