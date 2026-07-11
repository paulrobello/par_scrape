"""Tests for the queue-management CLI subcommands (ENH-006).

Drives the ``queue`` sub-app through CliRunner against the conftest ``db_path``
fixture (so ``~/.par_scrape/jobs.sqlite`` is never touched) and verifies the
backward-compat routing that keeps ``par_scrape -u URL`` working once a second
subcommand exists.
"""

from pathlib import Path

from typer.testing import CliRunner

from par_scrape import __version__
from par_scrape.__main__ import app
from par_scrape.crawl import add_to_queue, get_queue_stats, list_runs, mark_complete, mark_error

runner = CliRunner()


def _seed(db_path: Path) -> None:
    """Two runs: run1 with two errored pages, run2 with two completed pages."""
    add_to_queue("run1", ["https://example.com/a", "https://example.com/b"], db_path=db_path)
    mark_error("run1", "https://example.com/a", "timeout", db_path=db_path)
    mark_error("run1", "https://example.com/b", "dns failure", db_path=db_path)
    add_to_queue("run2", ["https://example.com/c", "https://example.com/d"], db_path=db_path)
    mark_complete(
        "run2",
        "https://example.com/c",
        raw_file_path=Path("/tmp/r.md"),
        file_paths={},
        db_path=db_path,
    )
    mark_complete(
        "run2",
        "https://example.com/d",
        raw_file_path=Path("/tmp/r.md"),
        file_paths={},
        db_path=db_path,
    )


def test_queue_list_shows_both_runs(db_path):
    _seed(db_path)
    result = runner.invoke(app, ["queue", "list"])
    assert result.exit_code == 0, result.output
    assert "run1" in result.output
    assert "run2" in result.output


def test_queue_list_empty_is_friendly(db_path):
    result = runner.invoke(app, ["queue", "list"])
    assert result.exit_code == 0
    assert "No runs found" in result.output


def test_queue_status_shows_error_rows(db_path):
    _seed(db_path)
    result = runner.invoke(app, ["queue", "status", "run1"])
    assert result.exit_code == 0, result.output
    assert "https://example.com/a" in result.output
    assert "https://example.com/b" in result.output


def test_queue_status_unknown_run(db_path):
    result = runner.invoke(app, ["queue", "status", "nope"])
    assert result.exit_code == 0
    assert "No such run" in result.output


def test_queue_retry_requeues_errors(db_path):
    _seed(db_path)
    result = runner.invoke(app, ["queue", "retry", "run1"])
    assert result.exit_code == 0, result.output
    assert "Requeued 2" in result.output
    stats = get_queue_stats("run1", db_path=db_path)
    assert stats["error"] == 0
    assert stats["queued"] == 2


def test_queue_reset_deletes_run(db_path):
    _seed(db_path)
    result = runner.invoke(app, ["queue", "reset", "run2", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Removed 2" in result.output
    runs = dict(list_runs(db_path=db_path))
    assert "run1" in runs
    assert "run2" not in runs


# ---------- backward-compat routing (the risk center of ENH-006) ----------


def test_bare_flags_route_to_scrape_version():
    """`par_scrape --version` still works once a second subcommand exists."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_explicit_scrape_command_help():
    """`par_scrape scrape --help` resolves the explicit scrape command."""
    result = runner.invoke(app, ["scrape", "--help"])
    assert result.exit_code == 0
    assert "URL to scrape" in result.output


def test_top_help_lists_scrape_and_queue():
    """`par_scrape --help` advertises both the scrape command and the queue group."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scrape" in result.output
    assert "queue" in result.output
