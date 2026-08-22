# Roadmap

> Phase-based development plan for Presidium.

## Philosophy

Documentation-driven development. Design docs and RFCs are written and reviewed before implementation begins. Each milestone (M) represents a coherent, shippable increment.

---

## M1: Foundation

**Goal:** Establish project identity, architecture, and documentation.

**Status:** Complete

- [x] Repository setup (monorepo, uv workspace, CI/CD)
- [x] AGENTS.md
- [x] Vision documents (manifesto, positioning, roadmap)
- [x] Architecture overview and package map
- [x] Interface-first architecture decisions (2-package structure, CEL default, library-first)
- [x] Competitive research archive
- [x] CNCF standards alignment principle (SPIFFE, OTEL, CEL)
- [ ] RFC-001: Presidium scope and boundaries (draft exists, needs finalization)
- [x] Design doc: Agent Registry (requirements + design + research, reviewed)
- [x] Design doc: Policy Engine (requirements + design, reviewed)
- [x] Design doc: Credential Provider (requirements + design)
- [x] Design doc: Approval Service (requirements + design)
- [x] Design doc: Audit Enricher (requirements + design)
- [x] Design doc: Topology Integration (requirements + design)
- [x] Agent registry industry research (AWS, Google, Microsoft, IBM, SPIFFE, K8s RBAC)
- [x] Full M2 design review (Oracle + consistency check, 12/12 issues resolved)
- [x] RFC-002: Multi-dimensional evaluation (seed for post-M4 investigation)
- [ ] Community feedback on architecture

**Deliverable:** Complete documentation. No code.

---

## M2: Core Interfaces + CEL Policy

**Goal:** All Protocol definitions in `presidium` core, plus working library-mode defaults. A developer can `pip install presidium` and have complete in-process governance.

**Status:** Complete. 245 tests, 95% coverage, mypy strict, ruff clean. Integration tests passing.

- [x] Requirements and design for all 9 components (35 design decisions, 12 review issues resolved)
- [x] `presidium` package — Protocol definitions + default implementations:
  - `AgentRegistry` + `InMemoryRegistry` / `SqliteRegistry` — SPIFFE-compatible `presidium://` identity, Ed25519 binding, K8s-style grants with CEL conditions, `trust_events` history table
  - `PolicyEngine` + `CelPolicyEngine` — 3 evaluation stages (pre_tool, pre_llm, registration), fail-closed, advisory/soft/hard enforcement modes, multi-stage rules
  - `CredentialProvider` + `EnvCredentialProvider` / `FileCredentialProvider` — grant-based credential access (`credential:{name}`), structured logging
  - `TrustScorer` + `LinearTrustScore` — 0.0-1.0, 3 tiers, lazy-on-read decay, materialize-on-write
  - `ApprovalService` + `CallbackApprovalProvider` — async HITL with 5-min default timeout, fail-closed
  - `AuditEnricher` + `InProcessAuditEnricher` — middleware sink, re-enrichment guard, fail-open enrichment
  - `GovernedModelProvider` — wraps ModelProvider, evaluates pre_llm policies
  - `GovernedToolProvider` — wraps ToolProvider, evaluates pre_tool policies
- [x] `GovernedRuntime` — programmatic constructor + `from_config()` YAML-based construction
- [x] 2 Civitas changes: add `"presidium"` to known keys + add `from_config_dict()` classmethod
- [x] Integration tests (compliant agent, denied agent, approval-gated, from_config YAML loading)
- [x] Getting started guide

**Deliverable:** `pip install presidium` — complete library-mode governance. No sidecars, no infrastructure, no Rego.

---

## M3: Contrib Adapters + Trust Scoring Foundation

**Goal:** `presidium-contrib` with adapters for existing products and reference implementations. Trust scoring enhancements for enterprise adoption: windowed aggregation, controllability, cold-start, spec introspection, bounded learning. Post-execution evaluation stages.

**Requirements:** [trust-scoring-requirements.md](../design/trust-scoring-requirements.md) (FR-3.1–3.8, FR-E.1–E.6)

- [x] `presidium-contrib` package (second workspace member)
- [x] Post-execution evaluation stages: `POST_TOOL`, `POST_LLM`
- [x] Adapters: `OPAPolicyEngine`, `OpenBaoCredentialProvider`, `AgentGatewayClient`, `SlackApprovalService`, `WebhookApprovalProvider`
- [x] Reference impls: `PostgresAgentRegistry`, `LearningTrustScorer` (refactored to use `presidium.scoring` library)
- [x] Trust scoring enhancements (presidium core):
  - Windowed aggregation — last N events or last T hours (FR-3.1)
  - Exponential decay opt-in with configurable half-life (FR-3.2)
  - Controllability filter — `controllable: bool` on events (FR-3.3)
  - Cold-start strategies — optimistic, neutral, pessimistic (FR-3.4)
  - Spec introspection — `IntrospectableScorer` Protocol with `ScoringSpec` + `spec_hash` (FR-3.5)
  - Bounded learning with max weight delta and rate limiting (FR-3.7)
  - Reason surfacing — `QueryableScorer` Protocol (FR-3.8)
- [x] Enterprise requirements:
  - Spec pinning for compliance periods (FR-E.1)
  - Override attribution — `actor_id` required on HUMAN_OVERRIDE (FR-E.2)
  - Performance budget — <1ms p99 reads (FR-E.3)
  - Zero-downtime M2→M3 migration (FR-E.4)
  - Determinism contract on scorers (FR-E.5)
  - OpenTelemetry spans for trust operations (FR-E.6)
- [ ] Deferred adapters: `CedarPolicyEngine`, `TemporalApprovalService`
- [x] `pre_message` evaluation stage (Civitas MessageBus hook via `GovernedMessageBus`)
- [x] MCP governance reference impl (tool poisoning, credential redaction, PII masking)
- [x] Service mode GenServer wrappers (`PolicyEvaluatorServer`, `RegistryServer`)
- [x] Policy hot-reload without restart (`GovernedRuntime.reload_policies()`)

**Deliverable:** `pip install presidium-contrib[opa,openbao,slack,agentgateway]` + enterprise-ready trust scoring

---

## M4: Autonomy Progression

![Autonomy Progression](../assets/autonomy-progression.svg)

**Goal:** Close the feedback loop. Agents earn autonomy through demonstrated reliability. Multi-dimensional trust scoring. Capability gating by tier. Decision journal for full auditability.

**Requirements:** [trust-scoring-requirements.md](../design/trust-scoring-requirements.md) (FR-4.1–4.6)

- [ ] Multi-dimensional trust scoring — `MultiDimensionalTrustScorer` Protocol with per-dimension scores and configurable aggregation (FR-4.1)
- [ ] Capability gating — tier-to-capability mapping via `CapabilityGate`, CEL references `agent.trust.capabilities` (FR-4.2)
- [ ] Graduated deactivation — `TierUpgraded`/`TierDegraded` events, subscriber pattern, no binary kill switch (FR-4.3)
- [ ] Confidence-gated routing — `ConfidenceRouter` selects agents or escalates to human (FR-4.4)
- [ ] Decision journal — all routing decisions and tier transitions recorded with trust snapshots (FR-4.5)
- [ ] Trust spec export — JSON, Markdown, detached JWS for tamper-evidence (FR-4.6)
- [ ] Heuristic-to-learned progression — `LearningTrustScorer` activates after data threshold
- [ ] Autonomy level API — agents query current level and promotion criteria
- [ ] Design doc: Autonomy Progression

**Deliverable:** Agents that start constrained and earn autonomy through behavior. Full decision audit trail.

---

## M5: SDK + CLI

**Goal:** One package, one install, complete experience. Trust CLI for operators.

**Requirements:** [trust-scoring-requirements.md](../design/trust-scoring-requirements.md) (FR-5.1–5.3)

- [ ] CLI: `presidium trust show`, `presidium trust events`, `presidium trust spec`, `presidium trust replay` (FR-5.1)
- [ ] Event export — JSON Lines, CSV with embedded `spec_hash` (FR-5.2)
- [ ] Deterministic replay — reproduce scores from historical events + spec (FR-5.3)
- [ ] CLI: `presidium run`, `presidium policy validate`, `presidium registry list`
- [ ] Comprehensive documentation site (MkDocs)
- [ ] Example applications (3-5 real-world scenarios)
- [ ] v1.0.0 release

**Deliverable:** `pip install presidium` — the full experience, documented and released.

---

## M6: Cloud

**Goal:** Managed service and enterprise features. Trust feedback loop measurement. Compliance reporting.

**Requirements:** [trust-scoring-requirements.md](../design/trust-scoring-requirements.md) (FR-6.1–6.4)

- [ ] Multi-tenant trust isolation — events, specs, audits partitioned by tenant (FR-6.1)
- [ ] Centralized event store — REST + gRPC, idempotent submissions (FR-6.2)
- [ ] Feedback loop metric — % of agents recovering from RESTRICTED to STANDARD+ (FR-6.3)
- [ ] Compliance reports — NIST AI RMF, ISO/IEC 42001 mappings (FR-6.4)
- [ ] Presidium Cloud (managed runtime + governance)
- [ ] Enterprise features (SSO, RBAC, SOC 2 compliance)
- [ ] Multi-region deployment
- [ ] SLA guarantees
- [ ] Pricing tiers (Free → Starter → Pro → Enterprise)

**Deliverable:** Commercial offering with trust analytics and compliance automation.

---

## M7: Presidium Server — self-hostable network governance service

**Goal:** Make Presidium's governance surface (policy evaluation, registry, approval,
credentials, trust) callable over a real network boundary by any properly authenticated
client — not just other Civitas agents in the same runtime. Today, `presidium`'s governance
components are only reachable in-process (as a library) or via Civitas's own actor-model
transport (Service Mode's `PolicyEvaluatorServer`/`RegistryServer` GenServers, reachable only
by other Civitas agents). **Neither of those is reachable by an external, non-Civitas system**,
which is a real, concrete blocker: `civitas-io/fabrica`'s `PresidiumClient` Protocol
(`check_grant()`) is fully specified and implementation-ready, but has nothing real to talk to.

**Not the same thing as M6.** M6 ("Cloud") is the commercial, multi-tenant SaaS offering —
Presidium Cloud, SSO, pricing tiers, SLAs. M7 is the underlying OSS building block: can
Presidium run as its own addressable, self-hosted, single-tenant process at all, reachable by
any authenticated caller. M6 would eventually run as a managed, multi-tenant deployment of
what M7 builds — not the reverse. Sequenced after M6 in this document because it was scoped
later, not because it is architecturally dependent on M6.

**Builds on real, existing work — this is a transport skin, not a rewrite:**

- Reuses `GovernedRuntime`'s existing composition (policy engine, registry, approval,
  credentials, trust) as the implementation behind every endpoint — no new governance logic.
- Reuses the existing `PolicyEvaluatorServer`/`RegistryServer` GenServer call protocol
  (`{"action": "evaluate", ...}` / `{"action": "lookup", ...}`) as the internal shape a REST
  facade translates to/from, rather than inventing a second evaluation path.
- Implements the AAA architecture already designed in
  [RFC-001](../rfcs/001-presidium-scope.md#aaa-architecture-holistic-view) and
  [`docs/research/aaa-patterns.md`](../research/aaa-patterns.md) — this milestone is "build the
  server RFC-001 already describes," not a new architecture decision.

**Requirements:**

- [ ] Design docs: `docs/design/presidium-server-requirements.md` + `presidium-server.md`,
  reviewed before implementation (per this project's own documentation-driven-development
  philosophy)
- [ ] Real decision, not silently picked: new standalone `presidium-server` package (own
  deployable process) vs. a `presidium-contrib[server]` extra — record as an ADR either way
- [ ] REST endpoints for all `GovernedRuntime` operations: `PRE_TOOL`/`PRE_LLM`/`PRE_MESSAGE`/
  `POST_TOOL`/`POST_LLM` evaluation, registry CRUD + grant management, approval
  request/list/decide, credential resolution
- [ ] **Must satisfy `civitas-io/fabrica`'s `PresidiumClient.check_grant()` contract exactly**:
  synchronous REST, `agent_id` + `action` + `scope` in,
  `GrantResult(decision, reason, approval_context)` out (confirmed directly against
  `civitas-io/fabrica/docs/contracts/managers.md`) — this is the first, most concrete consumer
  to build against, not a hypothetical one
- [ ] mTLS at the transport boundary, not bearer tokens/API keys as the primary mechanism —
  natural fit with `AgentRecord`'s existing SPIFFE-compatible `presidium://` identity model.
  **Real, pre-existing doc drift to resolve here, not before**: `docs/design/agent-registry.md`
  already describes a `presidium-contrib[spiffe]` extra ("M3+ upgrade path", real X.509-SVIDs
  via SPIRE) that **does not exist anywhere in the real codebase** — this milestone is where
  that extra would actually need to get built, not just referenced
- [ ] Preserve fail-closed semantics across the network boundary: an unreachable or erroring
  server must be something the *client* can safely treat as `deny` without the server needing
  to do anything special — Fabrica's own contract already assumes this ("never raises for a
  Presidium-unreachable condition"), so the server's only job is to be honest about its own
  health, not paper over outages
- [ ] Close the existing test-coverage gap first: `presidium_contrib.service.policy`/`.registry`
  (the GenServers this milestone wraps) currently have **0% test coverage** — a network-facing
  layer must not ship on top of untested internals
- [ ] Rate limiting / backpressure at the network boundary — a real concern for a shared
  network service that doesn't exist for an in-process library call

**Deliverable:** A real, self-hostable Presidium server process, reachable over REST+mTLS by
any authenticated external client (Civitas-based or not) — the concrete prerequisite that
unblocks Fabrica's `PresidiumClient` real implementation, and the technical foundation M6's
"Presidium Cloud" would eventually run as a managed, multi-tenant version of.

---

## Future Investigation: Multi-Dimensional Evaluation

> See [RFC-002](../rfcs/002-multi-dimensional-evaluation.md)

Current LLM evaluation collapses high-dimensional, non-deterministic outputs to scalar scores. This is a category error — the evaluation output should be distributional and multi-dimensional (per-dimension means with confidence intervals, context, and caveats), not a single number.

The M2 `TrustScorer` ships as a simple 0.0-1.0 scalar. Post-M4, investigate replacing scalar trust with distributional trust profiles: per-dimension scores with uncertainty bounds, context-dependent trust, and explicit caveats. This is a research-first effort — the questions in RFC-002 need answers before any design work.

---

## Timeline

These are aspirational, not commitments. Adjusted based on community feedback and contributor availability.

| Milestone | Target | Status |
|---|---|---|
| M1: Foundation | Q2 2026 | Complete |
| M2: Core Interfaces + CEL Policy | Q3 2026 | Complete |
| M3: Contrib Adapters + Reference Impls | Q3-Q4 2026 | Complete |
| M4: Autonomy Progression | Q4 2026 | Planning |
| M5: SDK + CLI | Q1 2027 | Planning |
| M6: Cloud | 2027+ | Future |
| M7: Presidium Server | TBD | Planning |
