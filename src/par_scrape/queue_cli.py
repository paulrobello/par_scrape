"""Queue-management CLI subcommands (ENH-006).

A ``par_scrape queue ...`` command group, registered from ``__main__.py``, that
makes the resume queue inspectable and repairable from the command line instead
of by hand-editing ``~/.par_scrape/jobs.sqlite``. Every command reads and writes
through the existing :mod:`par_scrape.queue_db` repository functions.
"""

import typer
from par_ai_core.par_logging import console_out
from rich.table import Table

from par_scrape.enums import PageStatus
from par_scrape.queue_db import (
    delete_run,
    get_queue_stats,
    get_run_pages,
    init_db,
    list_runs,
    requeue_errors,
)

queue_app = typer.Typer(help="Inspect and manage the crawl resume queue")

# How much of a row's error message to show in the status table; full messages
# can be long and the table is for triage.
_ERROR_PREVIEW_LEN = 80


@queue_app.command("list")
def list_command() -> None:
    """List every run in the queue with per-status page counts."""
    init_db()
    runs = list_runs()
    if not runs:
        console_out.print("[yellow]No runs found.[/yellow]")
        return

    table = Table(title="Crawl runs")
    table.add_column("Run", overflow="fold")
    for status in PageStatus:
        table.add_column(status.value.title(), justify="right")
    for ticket_id, counts in runs:
        table.add_row(ticket_id, *(str(counts.get(status.value, 0)) for status in PageStatus))
    console_out.print(table)


@queue_app.command("status")
def status_command(
    run_name: str = typer.Argument(..., help="The run name (ticket_id) to inspect."),
    show_all: bool = typer.Option(False, "--all", help="Include completed and queued rows, not just errors."),
) -> None:
    """Show per-status counts and the error rows for a run."""
    init_db()
    counts = get_queue_stats(run_name)
    if sum(counts.values()) == 0:
        console_out.print(f"[yellow]No such run:[/yellow] {run_name}")
        return

    summary = ", ".join(f"{counts[s.value]} {s.value}" for s in PageStatus)
    console_out.print(f"[bold]{run_name}[/bold]: {summary}")

    pages = get_run_pages(run_name)
    rows = [p for p in pages if show_all or p["status"] == PageStatus.ERROR.value]
    if not rows:
        console_out.print("[green]No error rows.[/green]" if not show_all else "[yellow]No rows to show.[/yellow]")
        return

    table = Table(title="Pages")
    table.add_column("URL", overflow="fold")
    table.add_column("Status")
    table.add_column("Error type")
    table.add_column("Error", overflow="fold")
    table.add_column("Attempts", justify="right")
    for p in rows:
        error_msg = (p["error_msg"] or "")[:_ERROR_PREVIEW_LEN]
        table.add_row(p["url"], p["status"], p["error_type"] or "-", error_msg, str(p["attempts"]))
    console_out.print(table)


@queue_app.command("retry")
def retry_command(
    run_name: str = typer.Argument(..., help="The run name whose errored pages should be requeued."),
) -> None:
    """Reset every errored page in a run back to queued."""
    init_db()
    requeued = requeue_errors(run_name)
    if requeued == 0:
        console_out.print(f"[yellow]No errored pages to retry in run:[/yellow] {run_name}")
        return
    console_out.print(f"[green]Requeued {requeued} errored page(s) in run[/green] {run_name}.")
    console_out.print(f"Resume with: par_scrape -u <url> --run-name {run_name} ...")


@queue_app.command("reset")
def reset_command(
    run_name: str = typer.Argument(..., help="The run name to delete from the queue."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete every page row for a run (destructive)."""
    init_db()
    counts = get_queue_stats(run_name)
    total = sum(counts.values())
    if total == 0:
        console_out.print(f"[yellow]No such run:[/yellow] {run_name}")
        return

    if not yes:
        confirm = typer.confirm(
            f"Delete {total} row(s) for run '{run_name}'? This cannot be undone (back up "
            f"~/.par_scrape/jobs.sqlite first if unsure).",
            default=False,
        )
        if not confirm:
            console_out.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit()

    removed = delete_run(run_name)
    console_out.print(f"[green]Removed {removed} row(s) for run[/green] {run_name}.")
