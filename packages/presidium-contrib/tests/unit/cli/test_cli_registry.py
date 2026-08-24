"""Unit tests for `presidium registry list` via Typer's CliRunner -- a real SqliteRegistry
database file, not mocked, matching civitas.cli's own established CliRunner pattern.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from typer.testing import CliRunner

from presidium.model import AgentRecord, Grant
from presidium.registry.sqlite import SqliteRegistry
from presidium_contrib.cli import app
from tests.unit.cli._helpers import unwrapped

runner = CliRunner()


def _seed_registry(db_path: Path) -> None:
    async def _seed() -> None:
        registry = SqliteRegistry(str(db_path))
        try:
            await registry.register(
                AgentRecord(
                    agent_id="presidium://acme.com/researcher",
                    name="researcher",
                    public_key="a2V5",
                    grants=[Grant(resources=["tool:database"], actions=["read"], id="g1")],
                )
            )
        finally:
            await registry.close()

    asyncio.run(_seed())


def test_registry_list_shows_a_real_seeded_agent(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    _seed_registry(db_path)

    result = runner.invoke(app, ["registry", "list", "--db", str(db_path)])

    # Real, deliberate: don't assert on the full agent_id string -- Rich's own Table wraps long
    # cell content across multiple lines depending on terminal width (confirmed directly: this
    # failed on the first real run for exactly that reason), matching civitas.cli's own test
    # suite's explicit lesson never to assert on rendered-text substrings that might wrap.
    assert result.exit_code == 0
    assert "researcher" in unwrapped(result.output)


def test_registry_list_nonexistent_db_exits_zero_with_a_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "does-not-exist.db"

    result = runner.invoke(app, ["registry", "list", "--db", str(db_path)])

    # Same real wrapping caveat as the seeded-agent test above -- a long tmp_path can wrap
    # across lines too. "does-not-exist.db" is short enough to never wrap in practice.
    assert result.exit_code == 0
    assert "No registry database found" in unwrapped(result.output)
    assert "does-not-exist.db" in unwrapped(result.output)


def test_registry_list_empty_registry(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"

    async def _touch() -> None:
        registry = SqliteRegistry(str(db_path))
        # Force real table creation with no agents registered -- confirmed this genuinely
        # creates the file/schema, not relying on an empty file already existing.
        await registry.list_agents()
        await registry.close()

    asyncio.run(_touch())

    result = runner.invoke(app, ["registry", "list", "--db", str(db_path)])

    assert result.exit_code == 0
