"""Output path computation for crawled URLs."""

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse


def get_url_output_folder(output_path: Path, ticket_id: str, url: str) -> Path:
    """
    Get storage folder based on URL and ticket_id.

    The URL is never mutated to derive the folder (ARC-003). All non-empty path
    segments are kept; when the resulting path would be long or the URL carries
    a query string, a short hash discriminator is appended so distinct URLs can
    never collide or nest.

    Args:
        output_path: Base path for output files
        ticket_id: Unique identifier for the crawl job
        url: The URL being processed

    Returns:
        Path: The folder path where output for this URL should be stored
    """
    # 1. Start with an absolute base folder - always use "./output"
    base_folder = output_path

    # 2. Add ticket_id once and only once
    run_folder = base_folder / ticket_id

    # 3. Parse the URL
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.split(":")[0]  # Remove port if present
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain) or ".." in domain:
        raise ValueError(f"Invalid URL host for output path: {domain!r}")

    # 4. Get path components. URLs are identifiers and are kept verbatim.
    raw_path = parsed_url.path.strip("/")

    # 5. If there's no path, just use the domain
    if not raw_path:
        return run_folder / domain

    # 6. Build a sanitized path from all non-empty path segments, converting
    #    slashes to double underscores.
    path_parts = raw_path.split("/")
    clean_parts = [part for part in path_parts if part != ""]

    sanitized_path = "__".join(clean_parts)

    # 7. Append a hash discriminator when the sanitized path is long or the URL
    #    carries a query string, so distinct URLs never collide or nest.
    if len(sanitized_path) > 100 or parsed_url.query:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        sanitized_path = f"{sanitized_path[:100]}-{digest}"

    # 8. Final path: ./output/ticket_id/domain/sanitized_path
    if sanitized_path:
        return run_folder / domain / sanitized_path
    else:
        return run_folder / domain
