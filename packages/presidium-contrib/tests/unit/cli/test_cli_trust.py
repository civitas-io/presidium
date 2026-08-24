"""Unit tests for `presidium trust replay` via Typer's CliRunner -- real event/spec JSON files,
real presidium.scoring.functions.replay(), not mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from presidium_contrib.cli import app
from tests.unit.cli._helpers import unwrapped

runner = CliRunner()

EVENTS = [
    {"id": "e1", "timestamp": "2026-08-20T10:00:00+00:00", "values": {"delta": 0.02}},
    {"id": "e2", "timestamp": "2026-08-21T10:00:00+00:00", "values": {"delta": 0.02}},
    {"id": "e3", "timestamp": "2026-08-22T10:00:00+00:00", "values": {"delta": -0.05}},
]

SPEC = {
    "scorer_type": "test",
    "initial_value": 0.5,
    "weights": {"success": 0.02, "failure": -0.05},
    "decay": {"function": "linear", "rate": 0.001},
}


def _write_json(tmp_path: Path, data: object, name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_replay_produces_a_real_deterministic_score(tmp_path: Path) -> None:
    events_path = _write_json(tmp_path, EVENTS, "events.json")
    spec_path = _write_json(tmp_path, SPEC, "spec.json")

    result = runner.invoke(
        app,
        [
            "trust",
            "replay",
            "--events",
            str(events_path),
            "--spec",
            str(spec_path),
            "--as-of",
            "2026-08-22T10:00:00+00:00",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "0.4420" in unwrapped(result.output)

    # Real determinism check (FR-5.3): running it again produces the exact same score.
    result2 = runner.invoke(
        app,
        [
            "trust",
            "replay",
            "--events",
            str(events_path),
            "--spec",
            str(spec_path),
            "--as-of",
            "2026-08-22T10:00:00+00:00",
        ],
    )
    assert result2.output == result.output


def test_replay_includes_the_real_spec_hash(tmp_path: Path) -> None:
    from presidium.scoring.config import DecayConfig
    from presidium.scoring.spec import ScoringSpec

    events_path = _write_json(tmp_path, EVENTS, "events.json")
    spec_path = _write_json(tmp_path, SPEC, "spec.json")

    result = runner.invoke(
        app, ["trust", "replay", "--events", str(events_path), "--spec", str(spec_path)]
    )

    assert result.exit_code == 0, result.output
    expected_spec = ScoringSpec(
        scorer_type="test",
        weights=SPEC["weights"],
        initial_value=SPEC["initial_value"],
        decay=DecayConfig(**SPEC["decay"]),
    )
    assert expected_spec.spec_hash in unwrapped(result.output)


def test_replay_events_with_context_field(tmp_path: Path) -> None:
    """Real, exercises EventContext(**item["context"]) -- never hit by the bare EVENTS fixture
    above, which has no "context" key on any event at all."""
    events_with_context = [
        {
            "id": "e1",
            "timestamp": "2026-08-20T10:00:00+00:00",
            "values": {"delta": 0.02},
            "context": {"controllable": True, "reason": "real test", "actor_id": "tester"},
        },
    ]
    events_path = _write_json(tmp_path, events_with_context, "events.json")
    spec_path = _write_json(tmp_path, SPEC, "spec.json")

    result = runner.invoke(
        app, ["trust", "replay", "--events", str(events_path), "--spec", str(spec_path)]
    )

    assert result.exit_code == 0, result.output


def test_replay_invalid_as_of_timestamp_fails(tmp_path: Path) -> None:
    """Real, exercises the ValueError branch of the except clause -- distinct from the
    KeyError/JSONDecodeError paths already covered above."""
    events_path = _write_json(tmp_path, EVENTS, "events.json")
    spec_path = _write_json(tmp_path, SPEC, "spec.json")

    result = runner.invoke(
        app,
        [
            "trust",
            "replay",
            "--events",
            str(events_path),
            "--spec",
            str(spec_path),
            "--as-of",
            "not-a-real-timestamp",
        ],
    )

    assert result.exit_code != 0


def test_replay_missing_events_file_fails(tmp_path: Path) -> None:
    spec_path = _write_json(tmp_path, SPEC, "spec.json")
    result = runner.invoke(
        app,
        ["trust", "replay", "--events", str(tmp_path / "nope.json"), "--spec", str(spec_path)],
    )
    assert result.exit_code == 1


def test_replay_missing_spec_file_fails(tmp_path: Path) -> None:
    events_path = _write_json(tmp_path, EVENTS, "events.json")
    result = runner.invoke(
        app,
        ["trust", "replay", "--events", str(events_path), "--spec", str(tmp_path / "nope.json")],
    )
    assert result.exit_code == 1


def test_replay_malformed_events_file_fails_with_a_helpful_message(tmp_path: Path) -> None:
    events_path = _write_json(tmp_path, [{"id": "e1"}], "bad_events.json")
    spec_path = _write_json(tmp_path, SPEC, "spec.json")

    result = runner.invoke(
        app, ["trust", "replay", "--events", str(events_path), "--spec", str(spec_path)]
    )

    assert result.exit_code == 1
    assert "missing required field" in unwrapped(result.output)
    assert "timestamp" in unwrapped(result.output)
