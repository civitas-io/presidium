from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from presidium.scoring.config import DecayConfig, ScoringConfig, WindowConfig
from presidium.scoring.events import Event, EventContext
from presidium.scoring.functions import clamp, decay, replay, score, windowed_score
from presidium.scoring.spec import ScoringSpec


def _event(
    event_type: str = "success",
    ts: datetime | None = None,
    delta: float | None = None,
    controllable: bool = True,
    tags: dict[str, str] | None = None,
) -> Event:
    t = tags or {}
    t["type"] = event_type
    values: dict[str, float] = {}
    if delta is not None:
        values["delta"] = delta
    return Event(
        id=str(uuid.uuid4()),
        timestamp=ts or datetime.now(UTC),
        tags=t,
        values=values,
        context=EventContext(controllable=controllable),
    )


TRUST_WEIGHTS: dict[str, float] = {
    "success": 0.02,
    "failure": -0.05,
    "policy_violation": -0.10,
}

TRUST_CONFIG = ScoringConfig(
    weights=TRUST_WEIGHTS,
    initial_value=0.5,
    decay=DecayConfig(function="linear", rate=0.01),
)


class TestClamp:
    def test_within_range(self) -> None:
        assert clamp(0.5) == 0.5

    def test_below_floor(self) -> None:
        assert clamp(-0.1) == 0.0

    def test_above_ceiling(self) -> None:
        assert clamp(1.5) == 1.0


class TestDecay:
    def test_linear_decay(self) -> None:
        result = decay(0.5, timedelta(hours=10), DecayConfig(function="linear", rate=0.01))
        assert result == pytest.approx(0.4, abs=0.001)

    def test_exponential_decay(self) -> None:
        result = decay(1.0, timedelta(hours=72), DecayConfig(function="exponential", rate=72.0))
        assert result == pytest.approx(0.5, abs=0.01)

    def test_no_elapsed_time(self) -> None:
        result = decay(0.5, timedelta(0), DecayConfig())
        assert result == 0.5

    def test_linear_floors_at_zero(self) -> None:
        result = decay(0.1, timedelta(hours=1000), DecayConfig(function="linear", rate=0.01))
        assert result == 0.0


class TestScore:
    def test_empty_events_returns_initial(self) -> None:
        result = score([], TRUST_CONFIG, as_of=datetime.now(UTC))
        assert result == pytest.approx(0.5, abs=0.001)

    def test_single_success(self) -> None:
        now = datetime.now(UTC)
        events = [_event("success", ts=now, delta=0.02)]
        result = score(events, TRUST_CONFIG, as_of=now)
        assert result == pytest.approx(0.52, abs=0.01)

    def test_single_failure(self) -> None:
        now = datetime.now(UTC)
        events = [_event("failure", ts=now, delta=-0.05)]
        result = score(events, TRUST_CONFIG, as_of=now)
        assert result == pytest.approx(0.45, abs=0.01)

    def test_sequence_of_events(self) -> None:
        now = datetime.now(UTC)
        events = [
            _event("success", ts=now, delta=0.02),
            _event("success", ts=now, delta=0.02),
            _event("failure", ts=now, delta=-0.05),
        ]
        result = score(events, TRUST_CONFIG, as_of=now)
        assert result == pytest.approx(0.49, abs=0.01)

    def test_decay_between_events(self) -> None:
        t0 = datetime.now(UTC) - timedelta(hours=10)
        t1 = datetime.now(UTC)
        events = [_event("success", ts=t0, delta=0.02)]
        # 0.5 + 0.02 = 0.52, then 10 hours decay at 0.01/hr = -0.10 → 0.42
        result = score(events, TRUST_CONFIG, as_of=t1)
        assert result == pytest.approx(0.42, abs=0.02)

    def test_clamped_at_bounds(self) -> None:
        now = datetime.now(UTC)
        events = [_event("success", ts=now, delta=0.9)]
        config = ScoringConfig(weights={}, initial_value=0.5)
        result = score(events, config, as_of=now)
        assert result <= 1.0

    def test_uses_weights_from_config(self) -> None:
        now = datetime.now(UTC)
        events = [_event("success", ts=now)]
        result = score(events, TRUST_CONFIG, as_of=now)
        assert result == pytest.approx(0.52, abs=0.01)

    def test_controllability_filter(self) -> None:
        now = datetime.now(UTC)
        events = [
            _event("failure", ts=now, delta=-0.05, controllable=False),
        ]
        unfiltered = score(events, TRUST_CONFIG, as_of=now, filter_uncontrollable=False)
        filtered = score(events, TRUST_CONFIG, as_of=now, filter_uncontrollable=True)
        assert unfiltered == pytest.approx(0.45, abs=0.01)
        assert filtered == pytest.approx(0.5, abs=0.01)


class TestWindowedScore:
    def test_respects_max_age(self) -> None:
        now = datetime.now(UTC)
        old = now - timedelta(hours=200)
        events = [
            _event("failure", ts=old, delta=-0.05),
            _event("success", ts=now, delta=0.02),
        ]
        window = WindowConfig(max_events=None, max_age_hours=168.0)
        result = windowed_score(events, TRUST_CONFIG, window=window, as_of=now)
        # Old failure aged out, only success in window
        assert result == pytest.approx(0.52, abs=0.01)

    def test_respects_max_events(self) -> None:
        now = datetime.now(UTC)
        events = [_event("failure", ts=now - timedelta(seconds=i), delta=-0.05) for i in range(10)]
        events.append(_event("success", ts=now, delta=0.02))
        window = WindowConfig(max_events=1, max_age_hours=None)
        result = windowed_score(events, TRUST_CONFIG, window=window, as_of=now)
        # Only the most recent event (success) in window
        assert result == pytest.approx(0.52, abs=0.01)

    def test_empty_window_returns_initial(self) -> None:
        now = datetime.now(UTC)
        old = now - timedelta(hours=1000)
        events = [_event("success", ts=old, delta=0.02)]
        window = WindowConfig(max_age_hours=1.0)
        result = windowed_score(events, TRUST_CONFIG, window=window, as_of=now)
        assert result == pytest.approx(0.5, abs=0.001)

    def test_no_window_uses_all_events(self) -> None:
        now = datetime.now(UTC)
        events = [_event("success", ts=now, delta=0.02)]
        result = windowed_score(events, TRUST_CONFIG, window=None, as_of=now)
        assert result == pytest.approx(0.52, abs=0.01)


class TestReplay:
    def test_replay_at_past_time(self) -> None:
        t0 = datetime.now(UTC) - timedelta(hours=2)
        t1 = datetime.now(UTC) - timedelta(hours=1)
        t2 = datetime.now(UTC)
        events = [
            _event("success", ts=t0, delta=0.02),
            _event("failure", ts=t1, delta=-0.05),
            _event("success", ts=t2, delta=0.02),
        ]
        # Replay at t1 — should only see first two events
        result = replay(events, TRUST_CONFIG, as_of=t1)
        # 0.5 + 0.02 (decay ~0.01) + (-0.05) ≈ 0.46
        assert 0.40 <= result <= 0.50

    def test_replay_deterministic(self) -> None:
        now = datetime.now(UTC)
        events = [_event("success", ts=now, delta=0.02)]
        r1 = replay(events, TRUST_CONFIG, as_of=now)
        r2 = replay(events, TRUST_CONFIG, as_of=now)
        assert r1 == r2

    def test_replay_with_window(self) -> None:
        now = datetime.now(UTC)
        old = now - timedelta(hours=200)
        events = [
            _event("failure", ts=old, delta=-0.05),
            _event("success", ts=now, delta=0.02),
        ]
        window = WindowConfig(max_age_hours=168.0)
        result = replay(events, TRUST_CONFIG, as_of=now, window=window)
        assert result == pytest.approx(0.52, abs=0.01)


class TestScoringSpec:
    def test_spec_hash_deterministic(self) -> None:
        s1 = ScoringSpec(scorer_type="linear", weights={"success": 0.02})
        s2 = ScoringSpec(scorer_type="linear", weights={"success": 0.02})
        assert s1.spec_hash == s2.spec_hash

    def test_spec_hash_changes_with_config(self) -> None:
        s1 = ScoringSpec(scorer_type="linear", weights={"success": 0.02})
        s2 = ScoringSpec(scorer_type="linear", weights={"success": 0.03})
        assert s1.spec_hash != s2.spec_hash

    def test_spec_is_frozen(self) -> None:
        s = ScoringSpec(scorer_type="linear")
        with pytest.raises(AttributeError):
            s.scorer_type = "other"  # type: ignore[misc]


class TestEventContext:
    def test_defaults(self) -> None:
        ctx = EventContext()
        assert ctx.controllable is True
        assert ctx.reason is None
        assert ctx.actor_id is None

    def test_frozen(self) -> None:
        ctx = EventContext(controllable=False, reason="test")
        with pytest.raises(AttributeError):
            ctx.controllable = True  # type: ignore[misc]
