"""Fetch HTML from URL and save it to a file."""

import logging
import os
import time

import html2text
from bs4 import BeautifulSoup
from par_ai_core.par_logging import console_out
from par_ai_core.user_agents import get_random_user_agent
from playwright.sync_api import expect, sync_playwright
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from .enums import WaitType


def setup_selenium(headless: bool = True) -> WebDriver:
    """Set up ChromeDriver for Selenium."""
    logger = logging.getLogger("selenium")
    logger.setLevel(logging.DEBUG)

    options = Options()

    # adding arguments
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-search-engine-choice-screen")
    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_experimental_option("excludeSwitches", ["enable-logging"])  # Disable logging
    options.add_argument("--silent")
    options.add_argument("--disable-extensions")

    # Enable headless mode if specified
    if headless:
        options.add_argument("--window-position=-2400,-2400")
        options.add_argument("--headless=new")

    # Randomize user-agent to mimic different users
    options.add_argument("user-agent=" + get_random_user_agent())

    try:
        chromedriver_path = ChromeDriverManager().install()
        # console_out.log(chromedriver_path)

        service = Service(chromedriver_path, log_output=os.devnull)

        # Initialize the WebDriver
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        console_out.print(f"[bold red]Error initializing Chrome WebDriver:[/bold red] {str(e)}")
        console_out.print("[yellow]Please ensure Chrome is installed and up to date.[/yellow]")
        console_out.print(
            "[yellow]Also, make sure the ChromeDriver version matches your Chrome browser version.[/yellow]"
        )
        raise


def fetch_html_selenium(
    url: str,
    headless: bool = True,
    wait_type: WaitType = WaitType.SLEEP,
    wait_selector: str | None = None,
    sleep_time: int = 3,
) -> str:
    """
    Fetch HTML content from a URL using Selenium.

    Args:
        url (str): The URL to fetch HTML content from.
        headless (bool, optional): Whether to run the browser in headless mode. Defaults to True.
        wait_type (WaitType, optional): The type of wait to use. Defaults to WaitType.SLEEP.
        wait_selector (Optional[str], optional): The CSS selector to wait for. Defaults to None.
        sleep_time (int, optional): The time to sleep in seconds. Defaults to 3.

    Returns:
        str: The fetched HTML content as a string.
    """
    driver = setup_selenium(headless)
    driver.set_script_timeout(30)

    try:
        driver.get(url)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

        try:
            # Wait for page to load
            if wait_type == WaitType.PAUSE:
                console_out.print("[yellow]Press Enter to continue...[/yellow]")
                input()
            elif wait_type == WaitType.SLEEP and sleep_time > 0:
                time.sleep(sleep_time)
            elif wait_type == WaitType.IDLE:
                time.sleep(1)
            elif wait_type == WaitType.SELECTOR:
                if wait_selector:
                    wait = WebDriverWait(driver, 10)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector)))
            elif wait_type == WaitType.TEXT:
                if wait_selector:
                    wait = WebDriverWait(driver, 10)
                    wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), wait_selector))

            # Scroll to bottom of page
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)  # Simulate time taken to scroll and read
        except TimeoutException:
            console_out.print("[yellow]Timed out waiting for condition.[/yellow]")

        return driver.page_source
    finally:
        driver.quit()


def fetch_html_playwright(
    url: str,
    headless: bool = True,
    wait_type: WaitType = WaitType.IDLE,
    wait_selector: str | None = None,
    sleep_time: int = 3,
) -> str:
    """
    Fetch HTML content from a URL using Playwright.

    Args:
        url (str): The URL to fetch HTML from.
        headless (bool, optional): Whether to run the browser in headless mode. Defaults to True.
        wait_type (WaitType, optional): The type of wait to use. Defaults to WaitType.IDLE.
        wait_selector (str, optional): The CSS selector to wait for. Defaults to None.
        sleep_time (int, optional): The sleep time in seconds. Defaults to 3.
    Returns:
        str: The HTML content of the page.
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless)
        except Exception as e:  # pylint: disable=broad-except
            console_out.print(
                "[bold red]Error launching playwright browser:[/bold red] Make sure you install playwright: `uv tool install playwright` then run `playwright install chromium`."  # pylint: disable=line-too-long
                # pylint: disable=line-too-long
            )
            raise e
            # return ["" * len(urls)]
        context = browser.new_context(viewport={"width": 1280, "height": 1024}, user_agent=get_random_user_agent())

        page = context.new_page()
        page.goto(url)

        if wait_type == WaitType.PAUSE:
            console_out.print("[yellow]Press Enter to continue...[/yellow]")
            input()
        elif wait_type == WaitType.SLEEP:
            # Add delays to mimic human behavior
            page.wait_for_timeout(sleep_time * 1000)  # Use the specified sleep time
        elif wait_type == WaitType.IDLE:
            page.wait_for_load_state("networkidle")  # domcontentloaded
        elif wait_type == WaitType.SELECTOR:
            if wait_selector:
                page.wait_for_selector(wait_selector)
            else:
                console_out.print(
                    "[bold yellow]Warning:[/bold yellow] Please specify a selector when using wait_type=selector."
                )
        elif wait_type == WaitType.TEXT:
            if wait_selector:
                expect(page.locator("body")).to_contain_text(wait_selector)
            else:
                console_out.print(
                    "[bold yellow]Warning:[/bold yellow] Please specify a selector when using wait_type=text."
                )

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
    for element in soup.find_all(
        [
            "header",
            "footer",
            "script",
            "source",
            "style",
            "head",
            "img",
            "svg",
            "iframe",
        ]
    ):
        element.decompose()  # Remove these tags and their content

    html_content = soup.prettify(formatter="html")

    ### text separators
    # Find all elements with role="separator"
    separator_elements = soup.find_all(attrs={"role": "separator"})

    # replace with <hr> element, markdown recognizes this
    for element in separator_elements:
        html_content = html_content.replace(str(element), "<hr>")

    return html_content


def html_to_markdown_with_readability(html_content: str) -> str:
    """
    Convert HTML content to Markdown format.

    Args:
        html_content (str): The HTML content to convert.

    Returns:
        str: The converted markdown content.
    """
    cleaned_html = clean_html(html_content)
    cleaned_html = cleaned_html.replace("<pre", "```<pre")
    cleaned_html = cleaned_html.replace("</pre>", "</pre>```")

    # Convert to markdown
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = markdown_converter.handle(cleaned_html)

    return markdown_content
