"""Web tools"""

from __future__ import annotations

import os
import time
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel
from rich.console import Console
from rich.repr import rich_repr

from .user_agents import get_random_user_agent

console = Console(stderr=True)


@rich_repr
class GoogleSearchResult(BaseModel):
    """Google search result."""

    title: str
    link: str
    snippet: str


def web_search(query: str, *, num_results: int = 3, verbose: bool = False) -> list[GoogleSearchResult]:
    """Google web search."""
    from langchain_google_community import GoogleSearchAPIWrapper

    if verbose:
        console.print(f"[bold green]Web search:[bold yellow] {query}")

    search = GoogleSearchAPIWrapper(
        google_cse_id=os.environ.get("GOOGLE_CSE_ID"),
        google_api_key=os.environ.get("GOOGLE_CSE_API_KEY"),
    )
    return [GoogleSearchResult(**result) for result in search.results(query, num_results=num_results)]


def get_html_element(element, soup: BeautifulSoup) -> str:
    """
    Searches for the first occurrence of a specified HTML element in a BeautifulSoup object and returns its text.

    Parameters:
    - element (str): The tag name of the HTML element to search for (e.g., 'h1', 'div').
    - soup (BeautifulSoup): A BeautifulSoup object containing the parsed HTML document.

    Returns:
    - str: The text of the first occurrence of the specified element if found; otherwise, an empty string.
    """
    result = soup.find(element)
    if result:
        return result.text

    # print(f"No element ${element} found.")
    return ""


def fetch_url(
    urls: str | list[str],
    *,
    fetch_using: Literal["playwright", "selenium"] = "playwright",
    sleep_time: int = 1,
    timeout: int = 10,
    verbose: bool = False,
) -> list[str]:
    """
    Fetch the contents of a webpage using either Playwright or Selenium.

    Args:
        urls (str | list[str]): The URL(s) to fetch.
        fetch_using (Literal["playwright", "selenium"]): The library to use for fetching the webpage.
        sleep_time (int): The number of seconds to sleep between requests.
        timeout (int): The number of seconds to wait for a response.
        verbose (bool): Whether to print verbose output.

    Returns:
        list[str]: A list of HTML contents of the fetched webpages.
    """
    if isinstance(urls, str):
        urls = [urls]
    if not all(urlparse(url).scheme for url in urls):
        raise ValueError("All URLs must be absolute URLs with a scheme (e.g. http:// or https://)")
    if fetch_using == "playwright":
        return fetch_url_playwright(urls, sleep_time=sleep_time, timeout=timeout, verbose=verbose)
    return fetch_url_selenium(urls, sleep_time=sleep_time, timeout=timeout, verbose=verbose)


def fetch_url_selenium(
    urls: str | list[str], *, sleep_time: int = 1, timeout: int = 10, ignore_ssl: bool = True, verbose: bool = False
) -> list[str]:
    """
    Fetch the contents of a webpage using Selenium.

    Args:
        urls (str | list[str]): The URL(s) to fetch.
        sleep_time (int): The number of seconds to sleep between requests.
        timeout (int): The number of seconds to wait for a response.
        ignore_ssl (bool): Whether to ignore SSL errors.
        verbose (bool): Whether to print verbose output.

    Returns:
        list[str]: A list of HTML contents of the fetched webpages.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    if isinstance(urls, str):
        urls = [urls]

    os.environ["WDM_LOG_LEVEL"] = "0"
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])  # Disable logging
    options.add_argument("--log-level=3")  # Suppress console logging
    options.add_argument("--silent")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    if ignore_ssl:
        options.add_argument("--ignore-certificate-errors")
    # Randomize user-agent to mimic different users
    options.add_argument("user-agent=" + get_random_user_agent())
    options.add_argument("--window-position=-2400,-2400")
    options.add_argument("--headless=new")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(timeout)

    results: list[str] = []
    for url in urls:
        if verbose:
            console.print(f"[bold blue]Selenium fetching content from {url}...[/bold blue]")
        try:
            driver.get(url)
            if verbose:
                console.print("[bold green]Page loaded. Scrolling and waiting for dynamic content...[/bold green]")
                console.print(f"[bold yellow]Sleeping for {sleep_time} seconds...[/bold yellow]")
            time.sleep(sleep_time)  # Sleep for the specified time
            # Scroll to the bottom of the page
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)  # Wait a bit for any dynamic content to load
            results.append(driver.page_source)
        except Exception as e:
            if verbose:
                console.print(f"[bold red]Error fetching content from {url}: {str(e)}[/bold red]")
            results.append("")
    try:
        driver.quit()
    except Exception as _:
        pass

    return results


def fetch_url_playwright(
    urls: str | list[str], *, sleep_time: int = 1, timeout: int = 10, ignore_ssl: bool = True, verbose: bool = False
) -> list[str]:
    """
    Fetch HTML content from a URL using Playwright.

    Args:
        urls (Union[str, list[str]]): The URL(s) to fetch.
        sleep_time (int, optional): The number of seconds to sleep between requests. Defaults to 1.
        timeout (int, optional): The timeout in seconds for the request. Defaults to 10.
        ignore_ssl (bool, optional): Whether to ignore SSL errors. Defaults to True.
        verbose (bool, optional): Whether to print verbose output. Defaults to False.

    Returns:
        list[str]: The fetched HTML content as a list of strings.
    """
    from playwright.sync_api import sync_playwright

    if isinstance(urls, str):
        urls = [urls]

    results: list[str] = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            console.print(
                "[bold red]Error launching playwright browser:[/bold red] Make sure you install playwright: `uv tool install playwright` then run `playwright install chromium`."
            )
            raise e
            # return ["" * len(urls)]
        context = browser.new_context(
            viewport={"width": 1280, "height": 1024}, user_agent=get_random_user_agent(), ignore_https_errors=ignore_ssl
        )

        page = context.new_page()
        for url in urls:
            if verbose:
                console.print(f"[bold blue]Playwright fetching content from {url}...[/bold blue]")
            try:
                page.goto(url, timeout=timeout * 1000)

                # Add delays to mimic human behavior
                if sleep_time > 0:
                    page.wait_for_timeout(sleep_time * 1000)  # Use the specified sleep time

                # Add more realistic actions like scrolling
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)  # Simulate time taken to scroll and read
                html = page.content()
                results.append(html)
                # if verbose:
                #     console.print(
                #         Panel(
                #             html[0:500] + "...",
                #             title="[bold green]Snippet[/bold green]",
                #         )
                #     )
            except Exception as e:
                if verbose:
                    console.print(f"[bold red]Error fetching content from {url}[/bold red]: {str(e)}")
                results.append("")
        try:
            browser.close()
        except Exception as _:
            pass

    return results


def fetch_url_and_convert_to_markdown(
    urls: str | list[str],
    *,
    fetch_using: Literal["playwright", "selenium"] = "playwright",
    include_links: bool = True,
    include_images: bool = False,
    include_metadata: bool = False,
    tags: list[str] | None = None,
    meta: list[str] | None = None,
    sleep_time: int = 1,
    timeout: int = 10,
    verbose: bool = False,
) -> list[str]:
    """
    Fetch the contents of a webpage and convert it to markdown.

    Args:
        urls (Union[str, list[str]]): The URL(s) to fetch.
        fetch_using (Literal["playwright", "selenium"], optional): The method to use for fetching the content. Defaults to "playwright".
        include_links (bool, optional): Whether to include links in the markdown. Defaults to True.
        include_images (bool, optional): Whether to include images in the markdown. Defaults to False.
        include_metadata (bool, optional): Whether to include a metadata section in the markdown. Defaults to False.
        tags (list[str], optional): A list of tags to include in the markdown metadata. Defaults to None.
        meta (list[str], optional): A list of metadata attributes to include in the markdown. Defaults to None.
        sleep_time (int, optional): The number of seconds to sleep between requests. Defaults to 1.
        timeout (int, optional): The timeout in seconds for the request. Defaults to 10.
        verbose (bool, optional): Whether to print verbose output. Defaults to False.

    Returns:
        list[str]: The converted markdown content as a list of strings.
    """
    import html2text

    if not tags:
        tags = []
    if not meta:
        meta = []

    if isinstance(urls, str):
        urls = [urls]
    pages = fetch_url(urls, fetch_using=fetch_using, sleep_time=sleep_time, timeout=timeout, verbose=verbose)
    sources = list(zip(urls, pages))
    if verbose:
        console.print("[bold green]Converting fetched content to markdown...[/bold green]")
    results: list[str] = []
    for url, html_content in sources:
        soup = BeautifulSoup(html_content, "html.parser")
        title = soup.title.text if soup.title else None

        if include_links:
            url_attributes = [
                "href",
                "src",
                "action",
                "data",
                "poster",
                "background",
                "cite",
                "codebase",
                "formaction",
                "icon",
            ]

            # Convert relative links to fully qualified URLs
            for tag in soup.find_all(True):
                for attribute in url_attributes:
                    if tag.has_attr(attribute):
                        attr_value = tag[attribute]
                        if attr_value.startswith("//"):
                            tag[attribute] = f"{url.split(':')[0]}:{attr_value}"
                        if not attr_value.startswith(("http://", "https://")):
                            tag[attribute] = urljoin(url, attr_value)

        metadata = {
            "source": url,
            "title": title or "",
            "tags": (" ".join(tags)).strip(),
        }
        for m in soup.find_all("meta"):
            n = m.get("name", "").strip()
            if not n:
                continue
            v = m.get("content", "").strip()
            if not v:
                continue
            if n in meta:
                metadata[n] = v

        elements_to_remove = [
            "head",
            "header",
            "footer",
            "script",
            "source",
            "style",
            "svg",
            "iframe",
        ]
        if not include_links:
            elements_to_remove.append("a")
            elements_to_remove.append("link")

        if not include_images:
            elements_to_remove.append("img")

        for element in elements_to_remove:
            for tag in soup.find_all(element):
                tag.decompose()

        html_content = soup.prettify(formatter="html")

        ### text separators
        # Find all elements with role="separator"
        separator_elements = soup.find_all(attrs={"role": "separator"})

        # replace with <hr> element, markdown recognizes this
        for element in separator_elements:
            html_content = html_content.replace(str(element), "<hr>")

        ### code blocks
        html_content = html_content.replace("<pre", "```<pre")
        html_content = html_content.replace("</pre>", "</pre>```")

        ### convert to markdown
        converter = html2text.HTML2Text()
        converter.ignore_links = not include_links
        converter.ignore_images = not include_images
        markdown = converter.handle(html_content)

        if include_metadata:
            meta_markdown = "# Metadata\n\n"
            for k, v in metadata.items():
                meta_markdown += f"- {k}: {v}\n"
            markdown = meta_markdown + markdown
        results.append(markdown)
    if verbose:
        console.print("[bold green]Conversion to markdown complete.[/bold green]")
    return results
