# Design: Trust Scoring System (M3-M4)

> Architecture for Presidium's trust scoring enhancements.
> Implements FR-3.1 through FR-3.8 and FR-E.1 through FR-E.6.
>
> Status: Draft — pending review
> Requirements: [trust-scoring-requirements.md](trust-scoring-requirements.md)
> Research: [trust-scoring-research.md](../research/trust-scoring-research.md)
> Last updated: 2026-06-14

---

## Design Principles

1. **Frozen Protocol is a feature.** `TrustScorer` (value, tier, last_updated, record_event) never changes. New capabilities = new Protocols.
2. **Composition over inheritance.** WindowedTrustScorer wraps any ReplayableScorer. No deep hierarchies.
3. **Spec captures config, journal captures history.** Specs are immutable. Current state is derived from spec + events.
4. **Clock injection everywhere.** No implicit `datetime.now()`. Determinism depends on it.
5. **Small, composable Protocols.** Scorers implement only what they need.

---

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected |
|---|---|---|---|
| T1 | Windowed aggregation location | Core, as wrapper over ReplayableScorer | Built into LearningTrustScorer only (limits reuse); mixin (complexity) |
| T2 | Controllability + frozen Protocol | Optional `context: EventContext` kwarg in ContextualTrustScorer Protocol | New enum values (enum bloat); separate method (fragmented API); post-hoc annotation (awkward) |
| T3 | Spec for learning scorers | Spec = immutable config; current weights = derived state from spec + journal | Spec captures current weights (hashes change constantly, pinning is meaningless) |
| T4 | Cold-start ↔ windowing | Linear blend during warmup: `(1-n/min)*cold_start + (n/min)*computed` | Hard switch (score discontinuity); no blending (cold-start value ignored after first event) |
| T5 | Core vs contrib | Protocols + WindowedTrustScorer + ColdStart in core; LearningTrustScorer + Journal in contrib | Everything in core (bloats core); everything in contrib (protocols not reusable) |
| T6 | Protocol granularity | Separate @runtime_checkable Protocols, mix and match | Single ExtendedTrustScorer (forces implementing unused methods) |

---

## Module Layout

```
presidium/src/presidium/
└── trust/                   # promote from single file to package
    ├── __init__.py           # re-exports: TrustScorer, LinearTrustScore, tier_for_value
    ├── core.py               # M2 FROZEN: TrustScorer Protocol, TrustEvent, TrustTier, tier_for_value
    ├── linear.py             # M2 base preserved + new compute_value() for ReplayableScorer
    ├── events.py             # EventContext, EventRecord, ValueExplanation
    ├── protocols.py          # ContextualTrustScorer, IntrospectableScorer,
    │                         # QueryableScorer, ReplayableScorer
    ├── spec.py               # ScoringSpec, WindowConfig, DecayConfig,
    │                         # ColdStartConfig, BoundedLearningConfig
    ├── cold_start.py         # ColdStartStrategy Protocol + OptimisticStart,
    │                         # NeutralStart, PessimisticStart
    └── windowed.py           # WindowedTrustScorer (wraps ReplayableScorer)

presidium-contrib/src/presidium_contrib/
└── trust/
    ├── scorer.py             # LearningTrustScorer (implements all Protocols)
    └── journal.py            # JournalEntry, LearningAudit, append-only log
```

Note: `trust.py` (current single file) gets promoted to `trust/` package. `trust/__init__.py` re-exports everything from `core.py` and `linear.py` so `from presidium.trust import TrustScorer, LinearTrustScore` still works.

---

## Protocol Definitions

### EventContext (FR-3.3, FR-E.2)

```python
@dataclass(frozen=True)
class EventContext:
    controllable: bool = True
    reason: str | None = None
    actor_id: str | None = None         # required for HUMAN_OVERRIDE (FR-E.2)
    correlation_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
```

### EventRecord

```python
@dataclass(frozen=True)
class EventRecord:
    event: TrustEvent
    timestamp: datetime
    context: EventContext | None = None
    delta_applied: float | None = None  # set post-hoc by scorer
```

### New Protocols

```python
@runtime_checkable
class ContextualTrustScorer(TrustScorer, Protocol):
    """Accepts rich per-event context. Extends frozen TrustScorer."""
    def record_event(
        self, event: TrustEvent, *, context: EventContext | None = None,
    ) -> None: ...

@runtime_checkable
class IntrospectableScorer(Protocol):
    """Exposes immutable config for audit and spec pinning."""
    @property
    def spec(self) -> ScoringSpec: ...

@runtime_checkable
class QueryableScorer(Protocol):
    """Surfaces reasons behind the current value."""
    def recent_events(self, limit: int = 10) -> list[EventRecord]: ...
    def explain_value(self) -> ValueExplanation: ...

@runtime_checkable
class ReplayableScorer(Protocol):
    """Pure function: same (events, now) → same value. No side effects.
    Required by WindowedTrustScorer. This is the determinism contract."""
    def compute_value(self, events: Sequence[EventRecord], now: datetime) -> float: ...
```

### ScoringSpec (FR-3.5, FR-E.1)

```python
@dataclass(frozen=True)
class ScoringSpec:
    scorer_fqn: str                                  # fully qualified class name
    spec_version: int                                # bump on structural changes
    initial_weights: Mapping[str, float]
    window: WindowConfig | None = None
    decay: DecayConfig = field(default_factory=DecayConfig)
    cold_start: ColdStartConfig = field(default_factory=ColdStartConfig)
    controllability_filter: bool = False
    bounded_learning: BoundedLearningConfig | None = None

    @cached_property
    def spec_hash(self) -> str:
        canonical = json.dumps(
            asdict(self), sort_keys=True,
            separators=(",", ":"), default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

---

## Windowed Aggregation (FR-3.1)

WindowedTrustScorer wraps a ReplayableScorer. It owns event storage (ring buffer) and cold-start blending. The inner scorer owns the math.

### Write path

```
caller.record_event(SUCCESS, context=EventContext(controllable=True))
  │
  ▼
WindowedTrustScorer.record_event
  1. Controllability filter: if spec.controllability_filter and not ctx.controllable → drop
  2. record = EventRecord(event, clock(), context)
  3. buffer.append(record)          ← deque caps at max_events
  4. n_seen_total += 1
```

### Read path

```
caller.value
  │
  ▼
WindowedTrustScorer.value
  1. now = clock()
  2. windowed = [r for r in buffer if r.timestamp >= now − max_age]
  3. n = len(windowed)
  4. Branch:
     n == 0         → cold_start.value(n_seen_total)
     n < min_normal → blend: (1-n/min)*cold_start + (n/min)*computed
     n >= min_normal → computed
  5. computed = inner.compute_value(windowed, now)
  6. clamp [0.0, 1.0]
```

### Decay inside inner

The inner ReplayableScorer handles decay during compute_value:

```
for each EventRecord (oldest → newest):
    value -= decay(event.timestamp − prev_timestamp)
    value += weights[event.event]
value -= decay(now − last_event.timestamp)
return clamp(value)
```

---

## Cold-Start (FR-3.4)

Three regimes based on `n` (events in window) and `min` (min_events_for_normal):

| Regime | Condition | Formula |
|---|---|---|
| Cold | n == 0 | `cold_start.value(n_seen_total)` |
| Warm-up | 0 < n < min | `(1 - n/min) * cold_start + (n/min) * computed` |
| Normal | n >= min | `computed` |

Set `min_events_for_normal = 0` to skip warm-up (single event → normal mode).

Uses `n_seen_total` (never decremented) so agents with events that aged out of the window still get credit for having existed.

### Strategies

```python
class ColdStartStrategy(Protocol):
    def initial_value(self) -> float: ...
    @property
    def min_events_for_normal(self) -> int: ...

class OptimisticStart:    initial=0.7, min_events=0
class NeutralStart:       initial=0.5, min_events=0    # M2 default
class PessimisticStart:   initial=0.2, min_events=5
```

---

## Spec Hash for Learning Scorers (T3)

Two hashes:

| Hash | What it captures | When it changes | Use |
|---|---|---|---|
| `spec_hash` | Immutable config (initial weights, decay, window, thresholds) | Never (spec is frozen at construction) | FR-E.1 spec pinning, audit |
| `state_hash` | `hash(spec_hash + journal_hash)` | Every learning invocation | Snapshot identity, cheap equality |

**Audit invariant:** `(spec, full_journal) → reproduces any historical value`.

To pin a scorer (FR-E.1), pin the `spec_hash`. To prove a value at time T (FR-E.5), replay events through a fresh inner built from the spec.

---

## Backward Compatibility

| What | Status |
|---|---|
| `from presidium.trust import TrustScorer, LinearTrustScore` | Works unchanged |
| `LinearTrustScore(initial_value=0.5)` | Same behavior, same defaults |
| `scorer.value`, `.tier`, `.last_updated`, `.record_event()` | Frozen |
| `agent.trust.value` / `agent.trust.tier` in CEL | Unchanged |
| `trust_events` table schema | Additive only (new optional columns) |

Adding `compute_value()` to LinearTrustScore is non-breaking — it's a new method, not a Protocol change.

---

## Effort Estimate

| Component | Effort |
|---|---|
| EventContext, EventRecord, ValueExplanation dataclasses | < 1 hour |
| New Protocols (4 definitions) | < 1 hour |
| ScoringSpec + sub-configs + spec_hash + canonical JSON tests | 2-4 hours |
| ColdStartStrategy + 3 impls | < 1 hour |
| WindowedTrustScorer (buffer, blend, clock, edge cases) | 1-2 days |
| LinearTrustScore.compute_value() retrofit | 2-4 hours |
| LearningTrustScorer refactor (all Protocols, bounded learning) | 1-2 days |
| JournalEntry + LearningAudit | 2-4 hours |
| Determinism property tests | 1-2 days |
| **Total** | **~5-8 days** |

---

## Risks

1. **Clock injection discipline.** Every component that reads time takes a `clock` parameter. Any implicit `datetime.now()` breaks determinism. Enforce via code review.
2. **spec_hash stability.** `json.dumps(sort_keys=True, separators=(",",":"))` is reliable, but `default=str` is fuzzy. Pin specific hashes in golden tests across Python 3.12/3.13.
3. **Cold-start blend can be gamed.** If agent learns it gets 0.7 from OptimisticStart, it might stay near zero events. Mitigated by `n_seen_total` — aged-out events still count.
4. **Learning weight drift.** 0.05/invocation × daily × 60 days = 3.0 total swing. FR-3.7 rate-limits invocations. Revisit if real-world drift exceeds expectations.
