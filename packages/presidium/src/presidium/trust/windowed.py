"""WindowedTrustScorer — stateful trust scorer using the scoring library."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from presidium.model import TrustEvent, TrustTier
from presidium.scoring.config import DecayConfig, ScoringConfig, WindowConfig
from presidium.scoring.events import Event, EventContext
from presidium.scoring.functions import clamp, windowed_score
from presidium.scoring.spec import ScoringSpec
from presidium.trust.cold_start import ColdStartStrategy, NeutralStart
from presidium.trust.core import tier_for_value

_TRUST_WEIGHTS: dict[str, float] = {
    "success": 0.02,
    "failure": -0.05,
    "policy_violation": -0.10,
}


class WindowedTrustScorer:
    """Stateful trust scorer with windowed aggregation and cold-start blending.

    Maintains an event buffer. Delegates scoring math to
    ``presidium.scoring.functions.windowed_score()``. Adds trust-specific
    cold-start blending and tier mapping.
    """

    def __init__(
        self,
        *,
        weights: dict[str, float] | None = None,
        initial_value: float | None = None,
        decay: DecayConfig | None = None,
        window: WindowConfig | None = None,
        cold_start: ColdStartStrategy | None = None,
        controllability_filter: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._weights = weights or dict(_TRUST_WEIGHTS)
        self._cold_start_strategy = cold_start or NeutralStart()
        self._initial_value = (
            initial_value
            if initial_value is not None
            else self._cold_start_strategy.initial_value()
        )
        self._decay = decay or DecayConfig()
        self._window = window or WindowConfig()
        self._cold_start = self._cold_start_strategy
        self._controllability_filter = controllability_filter
        self._clock = clock or (lambda: datetime.now(UTC))
        self._events: list[Event] = []
        self._n_seen: int = 0
        self._last_updated = self._clock()

    def record_event(self, event: TrustEvent, *, context: EventContext | None = None) -> None:
        now = self._clock()
        self._events.append(
            Event(
                id=str(uuid.uuid4()),
                timestamp=now,
                tags={"type": event.value},
                values={"delta": self._weights.get(event.value, 0.0)},
                context=context,
            )
        )
        self._n_seen += 1
        self._last_updated = now

    @property
    def value(self) -> float:
        now = self._clock()
        config = ScoringConfig(
            weights=self._weights,
            initial_value=self._initial_value,
            decay=self._decay,
            window=self._window,
        )

        computed = windowed_score(
            self._events,
            config,
            self._window,
            as_of=now,
            filter_uncontrollable=self._controllability_filter,
        )

        cs_val = self._initial_value
        min_n = self._cold_start.min_events_for_normal
        n = self._n_seen

        if n == 0:
            return clamp(cs_val)

        if min_n > 0 and n < min_n:
            blend = n / min_n
            return clamp((1 - blend) * cs_val + blend * computed)

        return clamp(computed)

    @property
    def tier(self) -> TrustTier:
        return tier_for_value(self.value)

    @property
    def last_updated(self) -> datetime:
        return self._last_updated

    @property
    def spec(self) -> ScoringSpec:
        return ScoringSpec(
            scorer_type="presidium.trust.windowed.WindowedTrustScorer",
            weights=dict(self._weights),
            initial_value=self._initial_value,
            decay=self._decay,
            window=self._window,
            controllability_filter=self._controllability_filter,
        )

    def recent_events(self, limit: int = 10) -> list[dict[str, object]]:
        recent = self._events[-limit:]
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "type": e.tags.get("type", ""),
                "delta": e.values.get("delta", 0.0),
                "controllable": e.context.controllable if e.context else True,
            }
            for e in reversed(recent)
        ]

    def set_value(self, value: float) -> None:
        now = self._clock()
        self._initial_value = clamp(value)
        self._events.clear()
        self._n_seen = 0
        self._last_updated = now
