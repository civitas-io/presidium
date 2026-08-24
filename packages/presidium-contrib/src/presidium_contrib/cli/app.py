"""Shared CLI application instance, consoles, and output helpers.

Every presidium_contrib.cli module imports from here -- the single source for the root Typer
app, Rich consoles, and consistent output formatting. Mirrors civitas.cli.app's own shape
exactly, adapted to Presidium's name/help text.
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="presidium",
    help="The governed agent platform built on Civitas.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()
err_console = Console(stderr=True)


def success(msg: str) -> None:
    """Print a success message with a green checkmark."""
    console.print(f"  [green]\u2714[/green] {msg}")


def error(msg: str) -> None:
    """Print an error message with a red X, to stderr."""
    err_console.print(f"  [red]\u2717[/red] {msg}")


def info(msg: str) -> None:
    """Print an info message in blue."""
    console.print(f"  [blue]{msg}[/blue]")


def warn(msg: str) -> None:
    """Print a warning message in yellow."""
    console.print(f"  [yellow]{msg}[/yellow]")


def section(title: str) -> None:
    """Print a section header (bold, indented)."""
    console.print(f"\n  [bold]{title}[/bold]")
