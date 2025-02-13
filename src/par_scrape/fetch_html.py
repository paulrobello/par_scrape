"""Fetch HTML from URL and save it to a file."""

import html2text
from bs4 import BeautifulSoup


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

    html_content = str(soup.prettify(formatter="html"))

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

    return markdown_content.strip()
