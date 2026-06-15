"""ScoringSpec — immutable config snapshot for audit and deterministic replay."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from functools import cached_property

from presidium.scoring.config import DecayConfig, WindowConfig


@dataclass(frozen=True)
class ScoringSpec:
    """Immutable scoring configuration. Hashable for audit pinning."""

    scorer_type: str
    spec_version: int = 1
    weights: Mapping[str, float] = field(default_factory=dict)
    initial_value: float = 0.5
    decay: DecayConfig = field(default_factory=DecayConfig)
    window: WindowConfig | None = None
    controllability_filter: bool = False

    @cached_property
    def spec_hash(self) -> str:
        data = asdict(self)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
