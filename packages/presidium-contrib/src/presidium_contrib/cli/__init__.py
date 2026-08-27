"""Presidium CLI -- command-line interface for the Presidium governance layer.

Built with Typer + Rich, mirroring `civitas-io/python-civitas`'s own `civitas.cli` package
directly -- same shared-`app.py`/one-module-per-command-group structure, same always-core
(not extra-gated) typer/rich dependency, matching this project's own AGENTS.md commitment to
following python-civitas conventions.

Lives in `presidium_contrib`, not `presidium` core: the core package is interface-only
(protocols, dataclasses, the one CEL policy engine exception) per this project's own established
boundary (AGENTS.md's own Anti-Patterns #9) -- a CLI is an operational tool, not an interface.

Package structure:
    app.py       -- shared Typer app, consoles, output helpers
    version.py   -- presidium version (a plain top-level command)
    registry.py  -- presidium registry list (a `registry` sub-app)
    policy.py    -- presidium policy validate (a `policy` sub-app)
    trust.py     -- presidium trust replay (a `trust` sub-app)

Real, honest scope note, not silently smaller than the design doc implies: `presidium trust
show`/`trust events` (the two FR-5.1 commands that query a LIVE agent's real event history) are
deliberately not built yet -- no registry backend today persists a durable, queryable trust-event
history (`LinearTrustScore`, the scorer every registry backend actually uses, keeps no event
log at all; `WindowedTrustScorer`, which does use `presidium.scoring`'s real event-based model,
is pure in-memory and not wired as anyone's default). Building those two commands for real needs
a durable event store first -- a real, separate, arguably-M4 (decision journal, FR-4.5) piece of
work, not a CLI gap. `trust replay` ships now because it operates on caller-supplied event/spec
files, not a live agent's history, so it needs no new persistence.
"""

from __future__ import annotations

import presidium_contrib.cli.version  # noqa: F401 -- registers `presidium version` directly
from presidium_contrib.cli.app import app
from presidium_contrib.cli.policy import policy_app
from presidium_contrib.cli.registry import registry_app
from presidium_contrib.cli.trust import trust_app

app.add_typer(registry_app, name="registry")
app.add_typer(policy_app, name="policy")
app.add_typer(trust_app, name="trust")


def main() -> None:
    """CLI entry point -- called by `[project.scripts] presidium`."""
    app()
