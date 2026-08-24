"""Unit tests for `presidium version` via Typer's CliRunner -- in-process, no subprocess,
mirroring civitas-io/python-civitas's own established test_cli.py pattern exactly (including
its own real lesson: never assert on Rich-rendered text substrings, since rendering width is
environment-dependent -- assert exit codes and real, controlled data values instead).
"""

from __future__ import annotations

from importlib.metadata import version as pkg_version

from typer.testing import CliRunner

from presidium_contrib.cli import app
from tests.unit.cli._helpers import unwrapped

runner = CliRunner()


def test_version_shows_both_real_package_versions() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert pkg_version("presidium") in unwrapped(result.output)
    assert pkg_version("presidium-contrib") in unwrapped(result.output)
