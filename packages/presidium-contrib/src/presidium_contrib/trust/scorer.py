"""LearningTrustScorer — trust scoring with adjustable weights and decision journal."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from presidium.model import TrustEvent, TrustTier
from presidium.trust import tier_for_value


@dataclass
class JournalEntry:
    event: TrustEvent
    value_before: float
    value_after: float
    tier_before: TrustTier
    tier_after: TrustTier
    timestamp: datetime
    context: dict[str, Any] = field(default_factory=dict)


class LearningTrustScorer:
    """Trust scorer with adjustable event weights and a decision journal.

    Starts with rule-based weights (same defaults as LinearTrustScore).
    Records every event in a journal. Weights can be adjusted via
    ``adjust_weights()`` or computed from journal history via
    ``learn_from_history()``.

    The learning algorithm: events followed by HUMAN_OVERRIDE (trust
    set higher) were too harsh — reduce their penalty. Events followed
    by HUMAN_OVERRIDE (trust set lower) were too lenient — increase
    their penalty. This creates a feedback loop where human corrections
    gradually tune the scoring model.
    """

    DEFAULT_WEIGHTS: dict[TrustEvent, float] = {
        TrustEvent.SUCCESS: 0.02,
        TrustEvent.FAILURE: -0.05,
        TrustEvent.POLICY_VIOLATION: -0.10,
    }

    def __init__(
        self,
        initial_value: float = 0.5,
        decay_rate: float = 0.01,
        weights: dict[TrustEvent, float] | None = None,
        *,
        _now: datetime | None = None,
    ) -> None:
        clamped = max(0.0, min(1.0, initial_value))
        now = _now or datetime.now(UTC)
        self._stored_value = clamped
        self._decay_rate = decay_rate
        self._weights = dict(weights or self.DEFAULT_WEIGHTS)
        self._last_positive_signal = now
        self._last_updated = now
        self._journal: list[JournalEntry] = []

    @property
    def value(self) -> float:
        elapsed_hours = (datetime.now(UTC) - self._last_positive_signal).total_seconds() / 3600.0
        return max(0.0, self._stored_value - self._decay_rate * elapsed_hours)

    @property
    def tier(self) -> TrustTier:
        return tier_for_value(self.value)

    @property
    def last_updated(self) -> datetime:
        return self._last_updated

    @property
    def weights(self) -> dict[TrustEvent, float]:
        return dict(self._weights)

    @property
    def journal(self) -> list[JournalEntry]:
        return list(self._journal)

    def record_event(self, event: TrustEvent, context: dict[str, Any] | None = None) -> None:
        now = datetime.now(UTC)
        value_before = self.value
        tier_before = self.tier

        self._stored_value = max(
            0.0,
            self._stored_value
            - self._decay_rate * (now - self._last_positive_signal).total_seconds() / 3600.0,
        )

        delta = self._weights.get(event)
        if delta is not None:
            self._stored_value = max(0.0, min(1.0, self._stored_value + delta))

        if event == TrustEvent.SUCCESS:
            self._last_positive_signal = now
        self._last_updated = now

        self._journal.append(
            JournalEntry(
                event=event,
                value_before=value_before,
                value_after=self.value,
                tier_before=tier_before,
                tier_after=self.tier,
                timestamp=now,
                context=context or {},
            )
        )

    def set_value(self, value: float) -> None:
        now = datetime.now(UTC)
        value_before = self.value
        tier_before = self.tier

        self._stored_value = max(0.0, min(1.0, value))
        self._last_positive_signal = now
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
        self._weights.update(new_weights)

    def learn_from_history(self, learning_rate: float = 0.1) -> dict[TrustEvent, float]:
        """Adjust weights based on HUMAN_OVERRIDE patterns in the journal.

        For each HUMAN_OVERRIDE, look at the preceding event. If the
        override raised trust, the preceding event's penalty was too
        harsh — reduce it. If the override lowered trust, the preceding
        event was too lenient — increase its penalty.

        Returns the new weights after adjustment.
        """
        adjustments: dict[TrustEvent, list[float]] = {}

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

        for event, directions in adjustments.items():
            if not directions:
                continue
            avg_direction = sum(directions) / len(directions)
            current = self._weights.get(event, 0.0)
            # If override raised trust → preceding penalty was too harsh → make less negative
            # If override lowered trust → preceding reward was too generous → make less positive
            self._weights[event] = current + (avg_direction * learning_rate)

        return dict(self._weights)
