"""Pure scoring functions. No state, no storage, no side effects."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timedelta

from presidium.scoring.config import DecayConfig, ScoringConfig, WindowConfig
from presidium.scoring.events import Event


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def decay(value: float, elapsed: timedelta, config: DecayConfig) -> float:
    hours = elapsed.total_seconds() / 3600.0
    if hours <= 0:
        return value
    if config.function == "exponential":
        half_life = config.rate if config.rate > 0 else 72.0
        return value * math.pow(0.5, hours / half_life)
    return max(0.0, value - config.rate * hours)


def _filter_window(
    events: Iterable[Event],
    window: WindowConfig | None,
    as_of: datetime,
) -> list[Event]:
    result = list(events)
    if window is None:
        return result

    if window.max_age_hours is not None:
        cutoff = as_of - timedelta(hours=window.max_age_hours)
        result = [e for e in result if e.timestamp >= cutoff]

    result.sort(key=lambda e: e.timestamp)

    if window.max_events is not None and len(result) > window.max_events:
        result = result[-window.max_events :]

    return result


def _filter_controllable(events: list[Event], filter_uncontrollable: bool) -> list[Event]:
    if not filter_uncontrollable:
        return events
    return [e for e in events if e.context is None or e.context.controllable]


def score(
    events: Iterable[Event],
    config: ScoringConfig,
    as_of: datetime | None = None,
    *,
    filter_uncontrollable: bool = False,
) -> float:
    """Compute a score from events. Pure function."""
    from datetime import UTC

    now = as_of or datetime.now(UTC)
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    sorted_events = _filter_controllable(sorted_events, filter_uncontrollable)

    value = config.initial_value
    prev_ts = sorted_events[0].timestamp if sorted_events else now

    for event in sorted_events:
        elapsed = event.timestamp - prev_ts
        value = decay(value, elapsed, config.decay)

        delta_key = event.tags.get("type", "")
        delta = config.weights.get(delta_key, 0.0)
        if "delta" in event.values:
            delta = event.values["delta"]
        value = clamp(value + delta)
        prev_ts = event.timestamp

    trailing = now - prev_ts
    if trailing > timedelta(0):
        value = decay(value, trailing, config.decay)

    return clamp(value)


def windowed_score(
    events: Iterable[Event],
    config: ScoringConfig,
    window: WindowConfig | None = None,
    as_of: datetime | None = None,
    *,
    filter_uncontrollable: bool = False,
) -> float:
    """Score only events within the window. Pure function."""
    from datetime import UTC

    now = as_of or datetime.now(UTC)
    windowed = _filter_window(events, window, now)
    windowed = _filter_controllable(windowed, filter_uncontrollable)

    if not windowed:
        return config.initial_value

    return score(windowed, config, as_of=now)


def replay(
    events: Iterable[Event],
    config: ScoringConfig,
    as_of: datetime,
    window: WindowConfig | None = None,
    *,
    filter_uncontrollable: bool = False,
) -> float:
    """Deterministic replay — reproduce a score at any point in time."""
    cutoff_events = [e for e in events if e.timestamp <= as_of]
    if window is not None:
        return windowed_score(
            cutoff_events,
            config,
            window,
            as_of=as_of,
            filter_uncontrollable=filter_uncontrollable,
        )
    return score(
        cutoff_events,
        config,
        as_of=as_of,
        filter_uncontrollable=filter_uncontrollable,
    )
