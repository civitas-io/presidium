"""Domain-agnostic event types for the scoring library."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class EventContext:
    """Optional context attached to a scoring event."""

    controllable: bool = True
    reason: str | None = None
    actor_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    """A single scored event. Domain-agnostic."""

    id: str
    timestamp: datetime
    tags: Mapping[str, str] = field(default_factory=dict)
    values: Mapping[str, float] = field(default_factory=dict)
    context: EventContext | None = None
