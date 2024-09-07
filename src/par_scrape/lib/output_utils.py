"""Output formatting utilities."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

from rich.syntax import Syntax
from rich.table import Table


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


def csv_file_to_table(csv_file: Path, title: Optional[str] = None) -> Table:
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
