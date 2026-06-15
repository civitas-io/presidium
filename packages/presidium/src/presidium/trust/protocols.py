"""Extended trust scoring Protocols (M3). All additive — TrustScorer is frozen."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from presidium.model import TrustEvent
from presidium.scoring.events import EventContext
from presidium.scoring.spec import ScoringSpec
from presidium.trust.core import TrustScorer


@runtime_checkable
class ContextualTrustScorer(TrustScorer, Protocol):
    """Extends TrustScorer with rich per-event context (FR-3.3, FR-E.2)."""

    def record_event(self, event: TrustEvent, *, context: EventContext | None = None) -> None: ...


@runtime_checkable
class IntrospectableScorer(Protocol):
    """Exposes immutable scoring config for audit and spec pinning (FR-3.5, FR-E.1, FR-E.5)."""

    deterministic: bool

    @property
    def spec(self) -> ScoringSpec: ...


@runtime_checkable
class QueryableScorer(Protocol):
    """Surfaces recent events and score explanation (FR-3.8)."""

    def recent_events(self, limit: int = 10) -> list[dict[str, object]]: ...
