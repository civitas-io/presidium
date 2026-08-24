# Requirements: Trust Scoring & Adaptive Autonomy

> Functional requirements for Presidium's trust scoring system across milestones.
> Based on research across production reputation systems, AI governance frameworks, and academic literature.
>
> Status: Draft
> Research: [trust-scoring-research.md](../research/trust-scoring-research.md)
> Last updated: 2026-06-14

---

## Pattern Decisions

10 universal patterns identified from eBay, Uber, FICO, Microsoft AGT, NIST, and academic research. Here's what Presidium implements and when:

| # | Pattern | Decision | Milestone | Rationale |
|---|---------|----------|-----------|-----------|
| 1 | Multi-dimensional scoring | Implement | M4 | Powerful but breaking. New `MultiDimensionalTrustScorer` Protocol; scalar remains default. |
| 2 | Temporal dynamics | Enhance | M3 | Add exponential decay opt-in. Keep linear as default. Lazy evaluation only. |
| 3 | Windowed aggregation | Implement | M3 | Foundational for LearningTrustScorer. All-time aggregation is a bug. |
| 4 | Controllability filter | Implement | M3 | Critical for fairness. `controllable: bool` on events. |
| 5 | Tier-based capability gating | Implement | M4 | Natural fit with autonomy progression. |
| 6 | Feedback loop measurement | Cut from core | M6 | Requires longitudinal data. Library mode can't measure it. Cloud scope. |
| 7 | Spec as auditable object | Implement | M3 | Single biggest enterprise unlock. |
| 8 | Cold-start mechanism | Implement | M3 | Trivial to add; blocks adoption. |
| 9 | Reversibility / graduated deactivation | Implement | M4 | Belongs with capability gating. |
| 10 | Transparency | Implement | M3 (basic) + M4 (full) | Reason field + query API in M3. Decision journal in M4. |

---

## Out of Scope

- **Cross-organization federated trust** — multi-year protocol design problem. Not Presidium's wedge.
- **ML-based prediction (deep learning)** — opaque, non-reproducible, regulatory liability. Learning limited to bounded statistical adjustment.
- **Background decay workers** — infrastructure dependency. Lazy decay only.
- **Webhook notifications for tier changes** — emit events; users wire their own notifications.
- **Trust scoring of humans** — scope creep.

---

## M3 Requirements — Extend Without Breaking

**FR-3.1 (Windowed Aggregation)** — Scorers SHALL support aggregating only the last N events (default 100) OR the last T hours (default 168h). Window strategy explicit at construction. Given identical event windows, scores SHALL be identical for deterministic scorers.

**FR-3.2 (Exponential Decay)** — System SHALL support exponential decay as opt-in, parameterized by half-life (default 72h). Decay applied lazily on read. `LinearTrustScore` retains its existing linear decay as default.

**FR-3.3 (Controllability Filter)** — `TrustEvent` SHALL gain optional `controllable: bool` (default `True`). Scorers MAY ignore `controllable=False` events. `LearningTrustScorer` MUST respect this field by default; `LinearTrustScore` ignores it (M2 compatibility).

**FR-3.4 (Cold-Start Strategies)** — `ColdStartStrategy` Protocol with three reference implementations:
- `OptimisticStart` (initial 0.7)
- `NeutralStart` (initial 0.5, current default)
- `PessimisticStart` (initial 0.2, requires N successes before tier can rise above RESTRICTED)

**FR-3.5 (Spec Introspection)** — `IntrospectableScorer` Protocol with `spec() -> ScoringSpec`. `ScoringSpec` is a frozen dataclass: event_weights, decay_function, decay_param, tier_thresholds, cold_start, window, spec_hash (SHA-256 of canonical JSON). `LinearTrustScore` and `LearningTrustScorer` MUST implement it.

**FR-3.6 (Learning Audit Log)** — `LearningTrustScorer.learn_from_history()` SHALL produce a `LearningAudit` per invocation: timestamp, events_considered, weight_changes (per-event-type before/after), max_delta_applied, rationale.

**FR-3.7 (Bounded Learning)** — `learn_from_history()` SHALL enforce `|weight_change| ≤ max_weight_delta` per event type per invocation (default 0.05). Cap exposed via `spec()`. Optional rate-limit (default: max 1/day).

**FR-3.8 (Reason Surfacing)** — `QueryableScorer` Protocol with `recent_events(limit: int = 20) -> list[TrustEvent]`. Implementations MUST preserve `reason` field. Enables agents and operators to read "why" without DB access.

---

## M4 Requirements — Autonomy Progression

**FR-4.1 (Multi-Dimensional Scoring)** — `MultiDimensionalTrustScorer` Protocol extends `TrustScorer` with `dimensions() -> Mapping[str, float]`. Dimensions are agent-author defined (string keys). Scalar `value` computed from dimensions via configurable `DimensionAggregator` (default: `min`; `mean` and `weighted_mean` provided).

**FR-4.2 (Capability Gating)** — `CapabilityGate` maps tiers to capability sets (default: RESTRICTED→{read}, STANDARD→{read,write}, TRUSTED→{read,write,execute}). CEL policies reference `agent.trust.capabilities`.

**FR-4.3 (Graduated Deactivation)** — Tier transitions emit typed events: `TierUpgraded`, `TierDegraded`. Subscribers register via `on_tier_change(handler)`. No built-in enforcement — emit events, let policy decide. Eliminates the binary kill switch.

**FR-4.4 (Confidence-Gated Routing)** — `ConfidenceRouter` accepts request + candidate agents, returns selected agent or `HumanEscalationRequired`. Selection considers tier, dimensions, and min-confidence threshold per request type.

**FR-4.5 (Decision Journal)** — All routing decisions and tier transitions recorded in `decision_journal` table: timestamp, decision_type, agent_id, trust_snapshot, inputs (hashed), outcome. Query API: `decisions(agent_id, since, limit)`.

**FR-4.6 (Trust Spec Export)** — `ScoringSpec` exports as JSON (machine), Markdown (human), detached JWS (tamper-evident). Export includes `spec_hash` for verification.

---

## M5 Requirements — SDK + CLI

**Status, 2026-08-24**: the first real `presidium` CLI shipped this day (`presidium_contrib.cli`,
`presidium` v0.4.0 / `presidium-contrib` v0.7.0). FR-5.3 is real and shipped as `presidium trust
replay --events <file> --spec <file>`. FR-5.1/FR-5.2 as originally specified below (querying a
*live agent's* history) are **not built, with a real, honest, confirmed reason, not an
oversight**: no registry backend today persists a durable, queryable trust-event history --
`LinearTrustScore` (the scorer every registry backend actually uses) keeps no event log at all;
`WindowedTrustScorer` (which does use the real `presidium.scoring` event-based model this FR
assumes) is pure in-memory and wired as no backend's default. Building `trust show`/`trust
events`/`trust spec <agent_id>` for real needs a durable event store first -- see
`docs/vision/roadmap.md`'s own M5 section for the full detail, and FR-4.5 (decision journal)
above for where that durability arguably belongs.

**FR-5.1 (CLI Trust Surface)** —
- `presidium trust show <agent_id>` → score, tier, dimensions, last 10 events
- `presidium trust events <agent_id> --since <date> --limit N`
- `presidium trust spec <agent_id> --format json|md`
- `presidium trust replay <agent_id> --until <date> --spec <path>`

**FR-5.2 (Event Export)** — `export_events(agent_id, format, since)` supports JSON Lines, CSV. Output embeds `spec_hash`.

**FR-5.3 (Deterministic Replay)** — `replay_score(events, spec) -> float` reproduces scores. For deterministic scorers, replayed scores match originals within 1e-9. **DONE, 2026-08-24** as `presidium trust replay --events <file> --spec <file>`, wrapping the real, pure, already-100%-tested `presidium.scoring.functions.replay()` directly (a real, honest re-scoping from `<agent_id>`-based to caller-supplied-file-based, for the same reason FR-5.1 above isn't built).

---

## M6 Requirements — Cloud

**FR-6.1 (Multi-Tenant Isolation)** — All trust artifacts partitioned by tenant_id.

**FR-6.2 (Centralized Event Store)** — REST + gRPC endpoints. Idempotent via event_id.

**FR-6.3 (Feedback Loop Metric)** — This is where Pattern #6 belongs: `% of agents that dropped to RESTRICTED and rose to STANDARD+ within N days`.

**FR-6.4 (Compliance Reports)** — NIST AI RMF, ISO/IEC 42001 mappings.

---

## Enterprise Cross-Cutting Requirements

**FR-E.1 (Spec Pinning)** [M3] — Operators MAY pin a scorer to a specific `spec_hash` for compliance periods. Spec mismatch raises `SpecMismatch`.

**FR-E.2 (Override Attribution)** [M3] — `HUMAN_OVERRIDE` events MUST include `actor_id: str`. Events without it raise `MissingAttribution`.

**FR-E.3 (Performance Budget)** [M3] — `TrustScorer.value` and `.tier` reads complete in <1ms p99 for in-memory implementations.

**FR-E.4 (Zero-Downtime Migration)** [M3] — Existing `trust_events` rows readable by M3+ scorers without re-scoring.

**FR-E.5 (Determinism Contract)** [M3] — Scorers declare `deterministic: bool`. `LinearTrustScore` → True. `LearningTrustScorer` → False. Replay guaranteed only for deterministic scorers.

**FR-E.6 (OpenTelemetry)** [M3] — Trust operations emit OTel spans/events with standardized attributes (`trust.agent_id`, `trust.event_type`, `trust.value`, `trust.tier`, `trust.spec_hash`).

---

## Backward Compatibility

1. **`TrustScorer` Protocol frozen** — `value`, `tier`, `last_updated`, `record_event`. New capabilities via new Protocols.
2. **`LinearTrustScore` M2 behavior preserved** — same defaults, same decay, same thresholds.
3. **`trust_events` schema additive only** — new columns optional with defaults. No backfill.
4. **CEL contract preserved** — `agent.trust.value`, `agent.trust.tier` unchanged. `agent.trust.capabilities` and `agent.trust.dimensions` are M4 additions.
5. **Event types append-only** — existing deltas in `LinearTrustScore` SHALL NOT change.

---

## Effort Estimates

| Milestone | Scope | Effort |
|---|---|---|
| M3 | FR-3.1–3.8, FR-E.1–E.6 | ~2 weeks |
| M4 | FR-4.1–4.6 | ~3-4 weeks |
| M5 | FR-5.1–5.3 | ~3-5 days |
| M6 | FR-6.1–6.4 | Separate effort (cloud) |
