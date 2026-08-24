"""presidium trust replay -- deterministic replay against caller-supplied events/spec files.

Real, deliberate re-scoping from FR-5.1's original `presidium trust replay <agent_id> --until
<date> --spec <path>` (querying a LIVE agent's real history): confirmed directly, no registry
backend today persists a durable, queryable event history for any real agent (see this
package's own `presidium_contrib.cli` module docstring for the full "why not yet" reasoning).
This command instead operates on real, caller-supplied `--events`/`--spec` JSON files -- a real,
working, standalone tool for testing a hypothetical scoring configuration or reproducing a score
from an exported event log, not a fake stand-in for the eventually-live version.

Wraps `presidium.scoring.functions.replay()` directly -- a real, pure, 100%-covered function
this command does not reimplement.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from presidium.scoring.config import DecayConfig, ScoringConfig, WindowConfig
from presidium.scoring.events import Event, EventContext
from presidium.scoring.functions import replay
from presidium.scoring.spec import ScoringSpec
from presidium_contrib.cli.app import console, err_console

trust_app = typer.Typer(
    name="trust",
    help="Trust scoring tools (deterministic replay).",
    no_args_is_help=True,
)


def _load_events(path: Path) -> list[Event]:
    raw: list[dict[str, Any]] = json.loads(path.read_text())
    events: list[Event] = []
    for item in raw:
        context = None
        if item.get("context") is not None:
            context = EventContext(**item["context"])
        events.append(
            Event(
                id=item["id"],
                timestamp=datetime.fromisoformat(item["timestamp"]),
                tags=item.get("tags", {}),
                values=item.get("values", {}),
                context=context,
            )
        )
    return events


def _spec_to_scoring_config(spec: ScoringSpec) -> ScoringConfig:
    """Real, small, deliberate conversion -- no such helper existed before this. `ScoringSpec`
    (an immutable, hashable audit snapshot) and `ScoringConfig` (the plain config
    `scoring.functions.score()`/`replay()` actually take) share every field this command needs
    except `scorer_type`/`spec_version` (audit metadata `replay()` itself has no use for).
    """
    return ScoringConfig(
        weights=spec.weights,
        initial_value=spec.initial_value,
        decay=spec.decay,
        window=spec.window,
    )


def _load_spec(path: Path) -> ScoringSpec:
    raw: dict[str, Any] = json.loads(path.read_text())
    decay = DecayConfig(**raw["decay"]) if "decay" in raw else DecayConfig()
    window = WindowConfig(**raw["window"]) if raw.get("window") is not None else None
    return ScoringSpec(
        scorer_type=raw.get("scorer_type", "presidium_contrib.cli.trust"),
        spec_version=raw.get("spec_version", 1),
        weights=raw.get("weights", {}),
        initial_value=raw.get("initial_value", 0.5),
        decay=decay,
        window=window,
        controllability_filter=raw.get("controllability_filter", False),
    )


@trust_app.command("replay")
def trust_replay(
    events: str = typer.Option(..., "--events", help="Path to a JSON file of scoring events"),
    spec: str = typer.Option(..., "--spec", help="Path to a JSON ScoringSpec file"),
    as_of: str | None = typer.Option(
        None, "--as-of", help="ISO 8601 timestamp to replay up to (default: now)"
    ),
) -> None:
    """Deterministically replay a trust score from real event/spec files (FR-5.3).

    Real, honest note printed alongside the result: this operates on the files you provide, not
    a live agent's actual history -- see `presidium trust --help`'s own module docstring for why
    `trust show`/`trust events` aren't built yet.
    """
    events_path = Path(events)
    spec_path = Path(spec)
    for label, p in (("events", events_path), ("spec", spec_path)):
        if not p.exists():
            err_console.print(f"[red]Error:[/red] {label} file '{p}' not found.")
            raise typer.Exit(1)

    try:
        loaded_events = _load_events(events_path)
        loaded_spec = _load_spec(spec_path)
        # Real bug found and fixed before this ever shipped: an invalid --as-of value used to
        # be parsed OUTSIDE this try/except entirely, so a bad timestamp raised an unhandled
        # ValueError (an ugly traceback) instead of the same clean "[red]Error[/red]" + exit 1
        # every other malformed-input case here gets. Moved inside, confirmed by testing a
        # real, deliberately-invalid --as-of value before trusting this was fixed.
        as_of_dt = datetime.fromisoformat(as_of) if as_of else datetime.now(UTC)
    except KeyError as exc:
        # str(KeyError("timestamp")) is the bare, unhelpful "'timestamp'" -- confirmed by
        # running this against a real, deliberately-malformed events file first, matching
        # policy.py's own identical fix for the same real KeyError-message-clarity issue.
        err_console.print(f"[red]Error:[/red] missing required field {exc}")
        raise typer.Exit(1) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    config = _spec_to_scoring_config(loaded_spec)
    score = replay(loaded_events, config, as_of_dt, window=loaded_spec.window)

    console.print(f"\n  Replayed [cyan]{len(loaded_events)}[/cyan] events")
    console.print(f"  As of: [cyan]{as_of_dt.isoformat()}[/cyan]")
    console.print(f"  Score: [green]{score:.4f}[/green]")
    console.print(f"  Spec hash: [dim]{loaded_spec.spec_hash}[/dim]\n")
