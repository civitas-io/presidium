"""Configuration types for the scoring library."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class DecayConfig:
    function: Literal["linear", "exponential"] = "linear"
    rate: float = 0.01


@dataclass(frozen=True)
class WindowConfig:
    max_events: int | None = 100
    max_age_hours: float | None = 168.0


@dataclass(frozen=True)
class ScoringConfig:
    weights: Mapping[str, float] = field(default_factory=dict)
    initial_value: float = 0.5
    decay: DecayConfig = field(default_factory=DecayConfig)
    window: WindowConfig | None = None
