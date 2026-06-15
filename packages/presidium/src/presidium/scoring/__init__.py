"""presidium.scoring — domain-agnostic scoring library.

Pure functions and lightweight types for computing scores from event streams.
Used by trust scoring, eval metrics, budget tracking, and compliance.
"""

from presidium.scoring.config import DecayConfig, ScoringConfig, WindowConfig
from presidium.scoring.events import Event, EventContext
from presidium.scoring.functions import decay, replay, score, windowed_score
from presidium.scoring.spec import ScoringSpec

__all__ = [
    "DecayConfig",
    "Event",
    "EventContext",
    "ScoringConfig",
    "ScoringSpec",
    "WindowConfig",
    "decay",
    "replay",
    "score",
    "windowed_score",
]
