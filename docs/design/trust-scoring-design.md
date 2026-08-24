# Design: Trust Scoring System (M3-M4)

> Architecture for Presidium's trust scoring enhancements.
> Implements FR-3.1 through FR-3.8 and FR-E.1 through FR-E.6.
>
> Status: Draft (revised) — scoring as a reusable library
> Requirements: [trust-scoring-requirements.md](trust-scoring-requirements.md)
> Research: [trust-scoring-research.md](../research/trust-scoring-research.md)
> Last updated: 2026-06-15

---

## Design Principles

1. **Frozen Protocol is a feature.** `TrustScorer` (value, tier, last_updated, record_event) never changes. New capabilities = new Protocols.
2. **Scoring logic as a reusable library.** Pure functions that compute scores from events. No infrastructure baked in. Trust, evals, budget, and compliance all use the same scoring primitives.
3. **Don't reinvent aggregation.** The scoring math is 20 lines of Python. Use plain Python for M3 library-mode (window of 100 events = microseconds). Add `presidium[fast]` with polars (Rust-backed) for M5/M6 batch replay at scale.
4. **Infrastructure is pluggable.** Events can come from memory, SQLite, Postgres, Kafka, Redis Streams — the library operates on `Iterable[Event]` and doesn't care.
5. **Spec captures config, journal captures history.** Specs are immutable. Current state is derived from spec + events.
6. **Clock injection everywhere.** No implicit `datetime.now()`. Determinism depends on it.
7. **Small, composable Protocols.** Scorers implement only what they need.

---

## Two-Layer Architecture

### Layer 1: Scoring Library (domain-agnostic, reusable)

Pure functions and lightweight stateful wrappers. No Presidium-specific concepts.

```
Event(id, timestamp, tags, values)
  → filter by tags
  → window by time or count
  → score(events, config) → float          PURE FUNCTION
  → scorer.ingest(event) → scorer.value    STATEFUL WRAPPER
  → replay(events, config, as_of) → float  DETERMINISTIC REPLAY
```

Consumers:
- Trust scoring (weighted decay + tiers)
- Eval metrics (pass rate + quality gates)
- Budget tracking (cost sum + caps)
- Compliance (policy compliance rate)

### Layer 2: Domain Layers (trust-specific, eval-specific, etc.)

Thin composition on top of Layer 1. Adds domain concepts:
- Trust: cold-start blending, tier mapping, capability gating
- Evals: version comparison, quality gates, correction signals
- Budget: hard caps, alerts, cost attribution

---

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected |
|---|---|---|---|
| T1 | Scoring engine | Pure Python functions + stateful wrapper. No custom aggregation framework. polars (Rust) as optional `[fast]` extra for M5/M6 batch replay. | Custom EventStore + WindowedTrustScorer wrapper (over-engineered); polars as core dep (30MB for trivial math) |
| T2 | Controllability + frozen Protocol | Optional `context: EventContext` kwarg in ContextualTrustScorer Protocol | New enum values (bloat); separate method (fragmented API) |
| T3 | Spec for learning scorers | Spec = immutable config; current weights = derived state from spec + journal | Spec captures current weights (hashes change, pinning meaningless) |
| T4 | Cold-start ↔ windowing | Linear blend during warmup: `(1-n/min)*cold_start + (n/min)*computed` | Hard switch (discontinuity) |
| T5 | Core vs contrib | Scoring primitives + Protocols in core; LearningTrustScorer in contrib | Everything in core (bloats it); everything in contrib (not reusable) |
| T6 | Protocol granularity | Separate @runtime_checkable Protocols, mix and match | Single ExtendedTrustScorer (forces unused methods) |
| T7 | Library vs platform | Scoring logic as reusable library. Trust, evals, budget are consumers. Don't build a platform — build the library, let M4 evals validate the abstraction. | Build unified scoring platform first (over-abstraction without second consumer) |
| T8 | Compute optimization | Pure Python for M3 (100 events × weighted sum = microseconds). polars as optional Rust-backed extra for batch operations. No custom Rust/C bindings. | polars as core dep (heavy for library); custom Rust (unnecessary until proven bottleneck) |

---

## Module Layout

```
presidium/src/presidium/
└── scoring/                 # NEW: domain-agnostic scoring library
    ├── __init__.py           # re-exports
    ├── events.py             # Event, EventContext, EventRecord
    ├── functions.py          # Pure scoring functions: score(), decay(), windowed_score()
    ├── config.py             # ScoringConfig, DecayConfig, WindowConfig
    └── spec.py               # ScoringSpec + spec_hash

└── trust/                   # promote from single file to package
    ├── __init__.py           # re-exports (backward compat: from presidium.trust import ...)
    ├── core.py               # M2 FROZEN: TrustScorer Protocol, TrustEvent, TrustTier
    ├── linear.py             # M2 LinearTrustScore (preserved) + compute_value() for replay
    ├── protocols.py          # ContextualTrustScorer, IntrospectableScorer, QueryableScorer
    ├── cold_start.py         # ColdStartStrategy + 3 impls
    └── windowed.py           # WindowedTrustScorer (thin: buffer + cold-start blend + delegates to scoring.functions)

presidium-contrib/src/presidium_contrib/
└── trust/
    ├── scorer.py             # LearningTrustScorer (implements all Protocols)
    └── journal.py            # JournalEntry, LearningAudit
```

Key insight: `presidium.scoring` is the reusable library. `presidium.trust` is one consumer. `presidium.eval` (M4) will be another consumer. Both import from `presidium.scoring`.

---

## Scoring Library Interface

### Pure Functions (no state, no storage)

```python
# presidium/scoring/functions.py

def score(
    events: Iterable[Event],
    config: ScoringConfig,
    as_of: datetime | None = None,
) -> float:
    """Compute a score from events. Pure function — no side effects."""

def windowed_score(
    events: Iterable[Event],
    config: ScoringConfig,
    window: WindowConfig,
    as_of: datetime | None = None,
) -> float:
    """Score only events within the window. Pure function."""

def decay(
    value: float,
    elapsed: timedelta,
    config: DecayConfig,
) -> float:
    """Apply decay to a value over elapsed time. Pure function."""

def replay(
    events: Iterable[Event],
    config: ScoringConfig,
    as_of: datetime,
) -> float:
    """Deterministic replay — reproduce a score at any point in time."""
```

### Event Schema (domain-agnostic)

```python
# presidium/scoring/events.py

@dataclass(frozen=True)
class Event:
    id: str
    timestamp: datetime
    tags: Mapping[str, str]      # {"agent": "x", "type": "success", "tool": "db"}
    values: Mapping[str, float]  # {"delta": 0.02, "cost_usd": 0.05}

@dataclass(frozen=True)
class EventContext:
    controllable: bool = True
    reason: str | None = None
    actor_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
```

### Config

```python
# presidium/scoring/config.py

@dataclass(frozen=True)
class DecayConfig:
    function: Literal["linear", "exponential"] = "linear"
    rate: float = 0.01           # linear: per hour; exponential: half-life in hours

@dataclass(frozen=True)
class WindowConfig:
    max_events: int | None = 100
    max_age_hours: float | None = 168.0  # 7 days

@dataclass(frozen=True)
class ScoringConfig:
    weights: Mapping[str, float]  # {"success": 0.02, "failure": -0.05, ...}
    initial_value: float = 0.5
    decay: DecayConfig = field(default_factory=DecayConfig)
    window: WindowConfig | None = None
```

---

## Trust Layer (thin consumer of scoring library)

```python
# presidium/trust/windowed.py

class WindowedTrustScorer:
    """Stateful trust scorer. Buffer + cold-start + delegates math to scoring.functions."""

    def __init__(self, config: TrustConfig, cold_start: ColdStartStrategy, *, clock=None):
        self._events: list[Event] = []
        self._config = config
        self._cold_start = cold_start
        self._clock = clock or (lambda: datetime.now(UTC))

    def record_event(self, event: TrustEvent, *, context: EventContext | None = None) -> None:
        self._events.append(_to_scoring_event(event, self._clock(), context))

    @property
    def value(self) -> float:
        now = self._clock()
        windowed = [e for e in self._events if _in_window(e, now, self._config.window)]
        n = len(windowed)

        if n == 0:
            return self._cold_start.initial_value()

        computed = windowed_score(windowed, self._config.scoring, self._config.window, now)

        if n < self._cold_start.min_events_for_normal:
            blend = n / self._cold_start.min_events_for_normal
            return clamp((1 - blend) * self._cold_start.initial_value() + blend * computed)

        return clamp(computed)

    @property
    def tier(self) -> TrustTier:
        return tier_for_value(self.value)
```

The trust layer is **~30 lines** of code that delegates to `scoring.functions`. It adds:
- Cold-start blending (trust concept)
- Tier mapping (trust concept)
- TrustEvent → Event conversion (trust concept)

Everything else — windowing, decay, scoring math — comes from the reusable library.

---

## Performance Analysis

| Operation | Events | Python time | Bottleneck? |
|---|---|---|---|
| `.value` read (hot path) | 100 (default window) | ~10μs | ❌ |
| `.value` read | 10K events | ~1ms | ❌ (at budget) |
| Batch replay 500 agents | 50M events | Minutes | ✅ Use polars |
| 1000 agents/sec scoring | 100K total events | ~10ms | ❌ |

**M3 decision:** Pure Python. The math is trivial at library-mode scale.
**M5/M6 decision:** Add `presidium[fast]` extra with polars (Rust-backed) for batch replay and cross-tenant aggregation.

---

## Backward Compatibility

| What | Status |
|---|---|
| `from presidium.trust import TrustScorer, LinearTrustScore` | Works unchanged |
| `LinearTrustScore(initial_value=0.5)` | Same behavior, same defaults |
| `scorer.value`, `.tier`, `.last_updated`, `.record_event()` | Frozen |
| `agent.trust.value` / `agent.trust.tier` in CEL | Unchanged |
| `trust_events` table schema | Additive only |

---

## What We Don't Build

- **Custom aggregation framework** — Python list comprehensions + basic math are sufficient
- **Custom EventStore** — events come from whatever the caller uses (list, SQLite, Postgres, Kafka)
- **Custom windowing engine** — a list filter is fine at 100 events; polars for batch at scale
- **Unified scoring platform** — build the library, prove it with trust, validate with evals in M4
- **Rust/C bindings** — polars IS Rust; no need for custom native code
- **Background workers** — lazy evaluation only

---

## Effort Estimate

| Component | Effort |
|---|---|
| `presidium.scoring` package (events, functions, config, spec) | 1-2 days |
| `presidium.trust` promotion to package + WindowedTrustScorer | 1-2 days |
| Protocol definitions (Contextual, Introspectable, Queryable) | < 1 day |
| ColdStartStrategy + 3 impls | < half day |
| LearningTrustScorer refactor to use scoring library | 1 day |
| Tests (determinism, windowing, cold-start, replay) | 1-2 days |
| **Total** | **~5-7 days** |
