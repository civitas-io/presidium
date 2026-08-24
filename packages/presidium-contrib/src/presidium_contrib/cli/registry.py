"""presidium registry -- inspect a local SQLite-backed agent registry.

Real, deliberate scope for this first pass, mirroring civitas.cli.state's own `civitas state
list --db <path>` almost exactly (same shape: a local SQLite file, no running server needed).
Deliberately does NOT talk to a live presidium-server's `/v1/agents` HTTP endpoint (the registry
CRUD work shipped in presidium-contrib v0.5.0) -- that's a real, separate, named follow-up
(`--server-url` mode), not silently promised here. This mode is the simpler, fully offline one:
point it at a real `SqliteRegistry` database file directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.table import Table

from presidium.errors import PresidiumError
from presidium.model import AgentRecord
from presidium_contrib.cli.app import console, error, warn

registry_app = typer.Typer(
    name="registry",
    help="Inspect a local SQLite-backed agent registry.",
    no_args_is_help=True,
)


async def _list_agents(db_path: str) -> list[AgentRecord]:
    # Lazy import, matching SqliteRegistry's own established pattern -- aiosqlite stays an
    # opt-in `presidium[sqlite]` dependency, not forced on every presidium-contrib install just
    # because the CLI happens to expose a subcommand that can use it.
    from presidium.registry.sqlite import SqliteRegistry

    registry = SqliteRegistry(db_path)
    try:
        return await registry.list_agents()
    finally:
        # Real bug found and fixed before this ever shipped: without this, aiosqlite's
        # background connection-worker thread outlives asyncio.run()'s own event loop
        # closing, and tries to call back into it -- a real, ugly "RuntimeError: Event loop
        # is closed" traceback printed after otherwise-correct output. Confirmed directly by
        # running this command without the close() call first.
        await registry.close()


@registry_app.command("list")
def registry_list(
    db: str = typer.Option(..., "--db", help="Path to a SqliteRegistry database file"),
) -> None:
    """List all agents in a local SQLite-backed registry."""
    db_path = Path(db)
    if not db_path.exists():
        warn(f"No registry database found at '{db}'.")
        raise typer.Exit(0)

    try:
        agents = asyncio.run(_list_agents(str(db_path)))
    except PresidiumError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    if not agents:
        warn("No agents registered.")
        return

    table = Table(title="Registered Agents", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Agent ID", style="white", overflow="fold")
    table.add_column("Status", style="white")
    table.add_column("Trust Tier", style="white")
    table.add_column("Trust Value", style="white", justify="right")
    table.add_column("Grants", style="white", justify="right")

    for agent in agents:
        table.add_row(
            agent.name,
            agent.agent_id,
            agent.status.value,
            agent.trust_tier.value,
            f"{agent.trust_value:.2f}",
            str(len(agent.grants)),
        )

    console.print(table)
