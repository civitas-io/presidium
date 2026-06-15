"""LearningTrustScorer — trust scoring with adjustable weights and decision journal."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from presidium.errors import MissingAttributionError
from presidium.model import TrustEvent, TrustTier
from presidium.scoring.config import DecayConfig, ScoringConfig, WindowConfig
from presidium.scoring.events import Event, EventContext
from presidium.scoring.functions import clamp, windowed_score
from presidium.scoring.spec import ScoringSpec
from presidium.trust.cold_start import ColdStartStrategy, NeutralStart
from presidium.trust.core import tier_for_value

_LEARNING_WEIGHTS: dict[str, float] = {
    "success": 0.02,
    "failure": -0.05,
    "policy_violation": -0.10,
}


@dataclass
class JournalEntry:
    event: TrustEvent
    value_before: float
    value_after: float
    tier_before: TrustTier
    tier_after: TrustTier
    timestamp: datetime
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningAudit:
    timestamp: datetime
    events_considered: int
    weight_changes: dict[str, tuple[float, float]]
    max_delta_applied: float
    rationale: str


class LearningTrustScorer:
    """Trust scorer with adjustable event weights and a decision journal.

    Delegates scoring math to ``presidium.scoring.functions``. Records every
    event in a journal. Weights can be adjusted via ``adjust_weights()`` or
    computed from journal history via ``learn_from_history()``.
    """

    deterministic: bool = False

    def __init__(
        self,
        initial_value: float = 0.5,
        weights: dict[TrustEvent, float] | None = None,
        *,
        decay: DecayConfig | None = None,
        window: WindowConfig | None = None,
        cold_start: ColdStartStrategy | None = None,
        max_weight_delta: float = 0.05,
        learn_cooldown_hours: float | None = 24.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cold_start_strategy = cold_start or NeutralStart()
        self._initial_value = max(0.0, min(1.0, initial_value))
        self._decay = decay or DecayConfig()
        self._window = window or WindowConfig()
        self._cold_start = self._cold_start_strategy
        self._max_weight_delta = max_weight_delta
        self._learn_cooldown_hours = learn_cooldown_hours
        self._last_learn_at: datetime | None = None
        self._clock = clock or (lambda: datetime.now(UTC))

        raw_weights = weights or {
            TrustEvent.SUCCESS: 0.02,
            TrustEvent.FAILURE: -0.05,
            TrustEvent.POLICY_VIOLATION: -0.10,
        }
        self._weights: dict[str, float] = {k.value: v for k, v in raw_weights.items()}

        self._events: list[Event] = []
        self._n_seen: int = 0
        self._last_updated = self._clock()
        self._journal: list[JournalEntry] = []
        self._learning_audits: list[LearningAudit] = []

    def _current_value(self) -> float:
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
            filter_uncontrollable=False,
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
    def value(self) -> float:
        return self._current_value()

    @property
    def tier(self) -> TrustTier:
        return tier_for_value(self.value)

    @property
    def last_updated(self) -> datetime:
        return self._last_updated

    @property
    def weights(self) -> dict[TrustEvent, float]:
        return {TrustEvent(k): v for k, v in self._weights.items()}

    @property
    def journal(self) -> list[JournalEntry]:
        return list(self._journal)

    def record_event(
        self,
        event: TrustEvent,
        *,
        context: EventContext | dict[str, Any] | None = None,
    ) -> None:
        if event == TrustEvent.HUMAN_OVERRIDE:
            if not isinstance(context, EventContext) or context.actor_id is None:
                raise MissingAttributionError()

        value_before = self.value
        tier_before = self.tier

        now = self._clock()
        ev_context: EventContext | None = None
        journal_context: dict[str, Any] = {}

        if isinstance(context, EventContext):
            ev_context = context
            journal_context = dict(context.metadata) if context.metadata else {}
            if context.reason:
                journal_context["reason"] = context.reason
            if context.actor_id:
                journal_context["actor_id"] = context.actor_id
        elif isinstance(context, dict):
            journal_context = context
            ev_context = EventContext(metadata={k: str(v) for k, v in context.items()})

        self._events.append(
            Event(
                id=str(uuid.uuid4()),
                timestamp=now,
                tags={"type": event.value},
                values={"delta": self._weights.get(event.value, 0.0)},
                context=ev_context,
            )
        )
        self._n_seen += 1
        self._last_updated = now

        self._journal.append(
            JournalEntry(
                event=event,
                value_before=value_before,
                value_after=self.value,
                tier_before=tier_before,
                tier_after=self.tier,
                timestamp=now,
                context=journal_context,
            )
        )

    def set_value(self, value: float) -> None:
        value_before = self.value
        tier_before = self.tier

        now = self._clock()
        self._initial_value = clamp(value)
        self._events.clear()
        self._n_seen = 0
        self._last_updated = now

        self._journal.append(
            JournalEntry(
                event=TrustEvent.HUMAN_OVERRIDE,
                value_before=value_before,
                value_after=self.value,
                tier_before=tier_before,
                tier_after=self.tier,
                timestamp=now,
                context={"set_value": value},
            )
        )

    def adjust_weights(self, new_weights: dict[TrustEvent, float]) -> None:
        for k, v in new_weights.items():
            self._weights[k.value] = v

    def learn_from_history(
        self,
        learning_rate: float = 0.1,
    ) -> dict[TrustEvent, float]:
        """Adjust weights based on HUMAN_OVERRIDE patterns in the journal.

        For each HUMAN_OVERRIDE, look at the preceding event. If the
        override raised trust, the preceding event's penalty was too
        harsh — reduce it. If the override lowered trust, the preceding
        event was too lenient — increase its penalty.

        Enforces |weight_change| <= max_weight_delta per event type (FR-3.7).
        Rate-limited by learn_cooldown_hours (default 24h, None to disable).
        """
        now = self._clock()
        if (
            self._learn_cooldown_hours is not None
            and self._last_learn_at is not None
            and (now - self._last_learn_at) < timedelta(hours=self._learn_cooldown_hours)
        ):
            return {TrustEvent(k): v for k, v in self._weights.items()}

        adjustments: dict[TrustEvent, list[float]] = {}
        events_considered = 0

        for i, entry in enumerate(self._journal):
            if entry.event != TrustEvent.HUMAN_OVERRIDE:
                continue
            if i == 0:
                continue

            prev = self._journal[i - 1]
            if prev.event == TrustEvent.HUMAN_OVERRIDE:
                continue

            override_direction = entry.value_after - entry.value_before
            adjustments.setdefault(prev.event, []).append(override_direction)
            events_considered += 1

        weight_changes: dict[str, tuple[float, float]] = {}
        max_delta = 0.0

        for event, directions in adjustments.items():
            if not directions:
                continue
            avg_direction = sum(directions) / len(directions)
            raw_change = avg_direction * learning_rate
            capped_change = max(-self._max_weight_delta, min(self._max_weight_delta, raw_change))
            before = self._weights.get(event.value, 0.0)
            self._weights[event.value] = before + capped_change
            weight_changes[event.value] = (before, before + capped_change)
            max_delta = max(max_delta, abs(capped_change))

        audit_now = self._clock()
        self._last_learn_at = audit_now
        self._learning_audits.append(
            LearningAudit(
                timestamp=audit_now,
                events_considered=events_considered,
                weight_changes=weight_changes,
                max_delta_applied=max_delta,
                rationale="human_override_feedback",
            )
        )

        return {TrustEvent(k): v for k, v in self._weights.items()}

    @property
    def spec(self) -> ScoringSpec:
        return ScoringSpec(
            scorer_type="presidium_contrib.trust.scorer.LearningTrustScorer",
            weights=dict(self._weights),
            initial_value=self._initial_value,
            decay=self._decay,
            window=self._window,
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

    @property
    def learning_audits(self) -> list[LearningAudit]:
        return list(self._learning_audits)
