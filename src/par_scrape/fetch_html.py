"""Fetch HTML from URL and save it to a file."""

import logging
import os
import random
import time

import html2text
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from .utils import console


def setup_selenium(headless: bool = True) -> WebDriver:
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

    try:
        chromedriver_path = ChromeDriverManager().install()

        service = Service(chromedriver_path, log_output=os.devnull)

        # Initialize the WebDriver
        driver = webdriver.Chrome(service=service, options=options)
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


def fetch_html_selenium(
    url: str, headless: bool = True, sleep_time: int = 5, pause: bool = False
) -> str:
    """Fetch HTML content from a URL using Selenium."""
    driver = setup_selenium(headless)
    try:
        driver.get(url)

        if pause:
            console.print("[yellow]Press Enter to continue...[/yellow]")
            input()
        else:
            # Add delays to mimic human behavior
            time.sleep(sleep_time)  # Use the specified sleep time

        # Add more realistic actions like scrolling
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(3, 5))  # Simulate time taken to scroll and read

        html = driver.page_source
        return html
    finally:
        driver.quit()


def fetch_html_playwright(
    url: str, sleep_time: int = 5, pause: bool = False
) -> str:
    """
    Fetch HTML content from a URL using Playwright.

    Args:
        url (str): The URL to fetch HTML from.

    Returns:
        str: The HTML content of the page.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        if pause:
            console.print("[yellow]Press Enter to continue...[/yellow]")
            input()
        else:
            # Add delays to mimic human behavior
            time.sleep(sleep_time)  # Use the specified sleep time

        # Add more realistic actions like scrolling
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)  # Simulate time taken to scroll and read

        html = page.content()
        browser.close()
        return html


def clean_html(html_content: str) -> str:
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


def html_to_markdown_with_readability(html_content: str) -> str:
    """
    Convert HTML content to Markdown format.

    Args:
        html_content (str): The HTML content to convert.

    Returns:
        str: The converted markdown content.
    """
    cleaned_html = clean_html(html_content)

    # Convert to markdown
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = markdown_converter.handle(cleaned_html)

    return markdown_content
