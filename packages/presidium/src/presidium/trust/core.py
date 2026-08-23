"""TrustScorer Protocol and LinearTrustScore default implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from presidium.model import TrustEvent, TrustTier

TIER_TRUSTED_THRESHOLD = 0.7
TIER_STANDARD_THRESHOLD = 0.3


def tier_for_value(value: float) -> TrustTier:
    if value >= TIER_TRUSTED_THRESHOLD:
        return TrustTier.TRUSTED
    if value >= TIER_STANDARD_THRESHOLD:
        return TrustTier.STANDARD
    return TrustTier.RESTRICTED


@runtime_checkable
class TrustScorer(Protocol):
    """Protocol for agent trust scoring.

    Implementations must expose the current trust value (0.0-1.0),
    the derived tier, the last update timestamp, and accept trust events.
    """

    @property
    def value(self) -> float: ...

    @property
    def tier(self) -> TrustTier: ...

    @property
    def last_updated(self) -> datetime: ...

    def record_event(self, event: TrustEvent) -> None: ...


class LinearTrustScore:
    """Default trust scorer with linear decay and 3 tiers.

    Deltas:
        SUCCESS: +0.02 (capped at 1.0)
        FAILURE: -0.05
        POLICY_VIOLATION: -0.10
        HUMAN_OVERRIDE: not applied via delta — use set_value() directly

    Decay: -0.01 per hour since last positive signal.
    Lazy-on-read: decay is computed when ``value`` is accessed.
    Materialize-on-write: decay is baked in before applying event deltas.
    """

    deterministic: bool = True

    _DELTAS: dict[TrustEvent, float] = {
        TrustEvent.SUCCESS: 0.02,
        TrustEvent.FAILURE: -0.05,
        TrustEvent.POLICY_VIOLATION: -0.10,
    }

    def __init__(
        self,
        initial_value: float = 0.5,
        decay_rate: float = 0.01,
        *,
        ceiling: float | None = None,
        _now: datetime | None = None,
    ) -> None:
        clamped = max(0.0, min(1.0, initial_value))
        now = _now or datetime.now(UTC)
        self._stored_value = clamped
        self._decay_rate = decay_rate
        self._ceiling = ceiling
        self._last_positive_signal = now
        self._last_updated = now

    @property
    def ceiling(self) -> float | None:
        """Upper bound on ``value`` (see ``presidium.lineage``). None means uncapped."""
        return self._ceiling

    @property
    def value(self) -> float:
        elapsed_hours = (datetime.now(UTC) - self._last_positive_signal).total_seconds() / 3600.0
        decayed = max(0.0, self._stored_value - self._decay_rate * elapsed_hours)
        if self._ceiling is not None:
            return min(decayed, self._ceiling)
        return decayed

    @property
    def tier(self) -> TrustTier:
        return tier_for_value(self.value)

    @property
    def last_updated(self) -> datetime:
        return self._last_updated

    def record_event(self, event: TrustEvent) -> None:
        now = datetime.now(UTC)
        # Materialize decay before applying delta
        self._stored_value = max(
            0.0,
            self._stored_value
            - self._decay_rate * (now - self._last_positive_signal).total_seconds() / 3600.0,
        )

        delta = self._DELTAS.get(event)
        if delta is not None:
            self._stored_value = max(0.0, min(1.0, self._stored_value + delta))

        if event == TrustEvent.SUCCESS:
            self._last_positive_signal = now
        self._last_updated = now

    def set_value(self, value: float) -> None:
        """Directly set the trust value (for HUMAN_OVERRIDE events).

        ``ceiling``, when set, still applies to the read path (``value``)
        even after a HUMAN_OVERRIDE -- a deliberate security choice: the
        entire purpose of a lineage-derived ceiling is "no scorer's value
        can rise above what its lineage permits," and a code path that
        silently lets any override bypass that would undermine the
        guarantee. An administrator who genuinely wants to grant a child
        more trust than its lineage permits must explicitly raise or clear
        ``AgentRecord.trust_ceiling`` itself -- a separate, deliberate
        administrative action, not something that happens implicitly here.
        """
        now = datetime.now(UTC)
        self._stored_value = max(0.0, min(1.0, value))
        self._last_positive_signal = now
        self._last_updated = now
