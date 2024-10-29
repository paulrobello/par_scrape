"""Output formatting utilities."""

from __future__ import annotations

import csv
import io
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table

console = Console(stderr=True)


class DisplayOutputFormat(str, Enum):
    """Enum for display output format choices."""

    MD = "md"
    CSV = "csv"
    JSON = "json"


def csv_to_table(data: str, title: str = "Results") -> Table:
    """Convert csv data to a table."""
    data = data.strip()
    table = Table(title=title)
    if not data:
        table.add_column("Empty", justify="left", style="cyan", no_wrap=True)
        return table
    reader = csv.DictReader(io.StringIO(data))
    if not reader.fieldnames:
        table.add_column("Empty", justify="left", style="cyan", no_wrap=True)
        return table
    data = list(reader)  # pyright: ignore
    for f in reader.fieldnames:
        table.add_column(f, justify="left", style="cyan", no_wrap=True)

    for row in data:
        table.add_row(*[v for n, v in row.items()])  # pyright: ignore
    return table


def csv_file_to_table(csv_file: Path, title: str | None = None) -> Table:
    """Convert csv file to a table."""
    return csv_to_table(
        csv_file.read_text(encoding="utf-8").strip(),
        csv_file.name if title is None else title,
    )


def highlight_json(data: str) -> Syntax:
    """Highlight JSON data."""
    return Syntax(data, "json", background_color="default")


def highlight_json_file(json_file: Path) -> Syntax:
    """Highlight JSON data."""
    return highlight_json(json_file.read_text(encoding="utf-8").strip())


def display_formatted_output(
    content: str, display_format: DisplayOutputFormat, out_console: Console | None = None
) -> None:
    """Display formatted output."""
    if not out_console:
        out_console = console

    if display_format == DisplayOutputFormat.MD:
        out_console.print(Markdown(content))
    elif display_format == DisplayOutputFormat.CSV:
        # Convert CSV to rich Table
        table = Table(title="CSV Data")
        csv_reader = csv.reader(io.StringIO(content))
        headers = next(csv_reader)
        for header in headers:
            table.add_column(header, style="cyan")
        for row in csv_reader:
            table.add_row(*row)
        out_console.print(table)
    elif display_format == DisplayOutputFormat.JSON:
        out_console.print(Syntax(content, "json"))
