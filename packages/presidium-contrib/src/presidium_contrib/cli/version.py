"""presidium version -- show the presidium/presidium-contrib versions."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from presidium_contrib.cli.app import app, console


@app.command()
def version() -> None:
    """Show the presidium and presidium-contrib versions.

    Real, deliberate difference from civitas's own `civitas version` (a single package):
    Presidium ships as two packages that can genuinely drift apart in version (presidium core
    stayed at v0.3.0 while presidium-contrib moved through v0.4.0-v0.6.0 this session) -- showing
    both, not just the one this CLI happens to live in, avoids a misleading single-version
    answer.
    """
    for package in ("presidium", "presidium-contrib"):
        try:
            v = _pkg_version(package)
        except PackageNotFoundError:  # running from a source tree without install
            v = "unknown (not installed)"
        console.print(f"[cyan]{package}[/cyan] version [green]{v}[/green]")
