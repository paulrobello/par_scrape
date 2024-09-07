"""Fetch HTML from URL and save it to a file."""

import json
import logging
import os
import asyncio
import random
from pathlib import Path

import aiofiles

import html2text
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from .utils import console


async def setup_selenium(headless: bool = True) -> WebDriver:
    """Set up ChromeDriver for Selenium."""

    logger = logging.getLogger("selenium")
    logger.setLevel(logging.DEBUG)

    options = Options()

    # adding arguments
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option(
        "excludeSwitches", ["enable-logging"]
    )  # Disable logging
    options.add_argument("--log-level=3")  # Suppress console logging
    options.add_argument("--silent")
    options.add_argument("--disable-extensions")

    # Enable headless mode if specified
    if headless:
        options.add_argument("--headless")

    # Randomize user-agent to mimic different users
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"  # pylint: disable=line-too-long
    )

    # Load ChromeDriver path from config.json
    config_path = Path("~/.par-scrape.config.json").expanduser()
    if config_path.exists():
        async with aiofiles.open(config_path, "rt", encoding="utf-8") as config_file:
            config = json.loads(await config_file.read())
            chromedriver_path = config.get("chromedriver_path", "")
    else:
        chromedriver_path = ""

    # Check if ChromeDriver exists, if not, download it
    if not chromedriver_path or not os.path.exists(chromedriver_path):
        console.print(
            "[yellow]ChromeDriver not found or path invalid. Attempting to download...[/yellow]"
        )
        try:
            chromedriver_path = await asyncio.to_thread(ChromeDriverManager().install)
            console.print(
                f"[green]ChromeDriver downloaded successfully to: {chromedriver_path}[/green]"
            )

            # Save the new path to config.json
            async with aiofiles.open(
                config_path, "wt", encoding="utf-8"
            ) as config_file:
                await config_file.write(
                    json.dumps({"chromedriver_path": chromedriver_path}, indent=4)
                )
            console.print("[green]Updated ChromeDriver path in config.json[/green]")
        except Exception as e:
            console.print(
                f"[bold red]Error downloading ChromeDriver:[/bold red] {str(e)}"
            )
            raise

    service = Service(chromedriver_path, log_output=os.devnull)

    try:
        # Initialize the WebDriver
        driver = await asyncio.to_thread(
            webdriver.Chrome, service=service, options=options
        )
        return driver
    except Exception as e:
        console.print(
            f"[bold red]Error initializing Chrome WebDriver:[/bold red] {str(e)}"
        )
        console.print(
            "[yellow]Please ensure Chrome is installed and up to date.[/yellow]"
        )
        console.print(
            "[yellow]Also, make sure the ChromeDriver version matches your Chrome browser version.[/yellow]"
        )
        raise


async def fetch_html_selenium(
    url: str, headless: bool = True, sleep_time: int = 5, pause: bool = False
) -> str:
    """Fetch HTML content from a URL using Selenium."""
    driver = await setup_selenium(headless)
    try:
        await asyncio.to_thread(driver.get, url)

        if pause:
            console.print("[yellow]Press Enter to continue...[/yellow]")
            await asyncio.to_thread(input)
        else:
            # Add delays to mimic human behavior
            await asyncio.sleep(sleep_time)  # Use the specified sleep time

        # Add more realistic actions like scrolling
        await asyncio.to_thread(
            driver.execute_script, "window.scrollTo(0, document.body.scrollHeight);"
        )
        await asyncio.sleep(
            random.uniform(3, 5)
        )  # Simulate time taken to scroll and read

        html = await asyncio.to_thread(lambda: driver.page_source)
        return html
    finally:
        await asyncio.to_thread(driver.quit)


async def fetch_html_playwright(
    url: str, sleep_time: int = 5, pause: bool = False
) -> str:
    """
    Fetch HTML content from a URL using Playwright.

    Args:
        url (str): The URL to fetch HTML from.

    Returns:
        str: The HTML content of the page.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)

        if pause:
            console.print("[yellow]Press Enter to continue...[/yellow]")
            await asyncio.to_thread(input)
        else:
            # Add delays to mimic human behavior
            await asyncio.sleep(sleep_time)  # Use the specified sleep time

        # Add more realistic actions like scrolling
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(3)  # Simulate time taken to scroll and read

        html = await page.content()
        await browser.close()
        return html


async def clean_html(html_content: str) -> str:
    """
    Clean HTML content by removing headers and footers.

    Args:
        html_content (str): The raw HTML content.

    Returns:
        str: The cleaned HTML content.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove headers and footers based on common HTML tags or classes
    for element in soup.find_all(["header", "footer"]):
        element.decompose()  # Remove these tags and their content

    return str(soup)


async def html_to_markdown_with_readability(html_content: str) -> str:
    """
    Convert HTML content to Markdown format.

    Args:
        html_content (str): The HTML content to convert.

    Returns:
        str: The converted markdown content.
    """
    cleaned_html = await clean_html(html_content)

    # Convert to markdown
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = await asyncio.to_thread(markdown_converter.handle, cleaned_html)

    return markdown_content
