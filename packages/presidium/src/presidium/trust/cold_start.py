"""Cold-start strategies for new agents with no trust history (FR-3.4)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ColdStartStrategy(Protocol):
    """Determines initial trust value and warmup behavior for new agents."""

    def initial_value(self) -> float: ...

    @property
    def min_events_for_normal(self) -> int: ...


class OptimisticStart:
    def initial_value(self) -> float:
        return 0.7

    @property
    def min_events_for_normal(self) -> int:
        return 0


class NeutralStart:
    def initial_value(self) -> float:
        return 0.5

    @property
    def min_events_for_normal(self) -> int:
        return 0


class PessimisticStart:
    def __init__(self, min_events: int = 5) -> None:
        self._min_events = min_events

    def initial_value(self) -> float:
        return 0.2

    @property
    def min_events_for_normal(self) -> int:
        return self._min_events
