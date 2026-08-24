# Roadmap

> Phase-based development plan for Presidium.

## Philosophy

Documentation-driven development. Design docs and RFCs are written and reviewed before implementation begins. Each milestone (M) represents a coherent, shippable increment.

---

## Implementation Priority (P0 / P1 / P2)

> Added 2026-08-22, after a full cross-project completion review (part of a wider effort covering
> `python-civitas`, `presidium`, and `fabrica` together — see `civitas-io/context`). This section
> is orthogonal to the M-numbered milestones below: it says **what order to actually do things in**
> to reach a genuinely complete, trustworthy Presidium, which cuts across several milestones at
> once. The M-sections remain the source of truth for scope; this section is the source of truth
> for sequencing and urgency.

### P0 — blocks calling Presidium "complete." Fix before anything else.

These are either **correctness/trust gaps hiding behind claims of completeness**, or the single
structural blocker to the three-pillar platform (Civitas + Presidium + Fabrica) working end to end.

- [x] **Fix the Ed25519 identity binding.** ~~`GovernedRuntime.start()` hardcodes
  `AgentRecord(public_key="", ...)`~~ **Done 2026-08-22.** `GovernedRuntime` now generates/loads a
  real, persistent `civitas.security.identity.AgentIdentity` per agent (`AgentIdentity.
  load_or_generate(name, key_dir)`, default `key_dir=.presidium/keys`, overridable via
  `presidium.registry.key_dir` in topology YAML or the constructor directly) and binds its real
  `public_key_b64()` into `AgentRecord.public_key`. `AgentRegistry` gained a real
  `verify_signature(name, data, signature) -> bool` method (shared implementation in the new
  `presidium.identity` module, fail-closed-as-a-plain-return-value like `has_grant()` — never
  raises), implemented in `InMemoryRegistry`, `SqliteRegistry`, and
  `presidium-contrib`'s `PostgresAgentRegistry`. 18 new real tests (real Ed25519 keypairs, real
  sign/verify round trips, persistence-across-restarts, tampered-data/wrong-key/malformed-key/
  missing-pynacl failure paths). **Found and fixed a real, separate, pre-existing bug while doing
  this work**: `presidium_contrib.service.registry.RegistryServer` named its own governance
  registry attribute `self._registry`, colliding with `civitas.process.AgentProcess`'s own
  reserved `_registry` attribute (Civitas's internal name-routing registry) — a real Supervisor
  wiring a `RegistryServer` into a live tree would silently clobber one with the other. Renamed to
  `self._agent_registry`; caught by mypy only after the `civitas` PyPI-pin fix below made
  `civitas`'s real `py.typed` marker visible for the first time. `.gitignore` gained `.presidium/`
  (real private key material must never be committable, even by accident). Coverage: presidium
  core 90.97% → **95.24%**.
- [x] **Pin `civitas` to a real PyPI release, not `git`/`branch = "main"`.** **Done 2026-08-22.**
  Removed the `[tool.uv.sources]` git override from the workspace root; bumped
  `presidium`'s own dependency from `civitas>=0.3` to `civitas>=0.11.0` (the real, current,
  tested-against version — matches `civitas-io/fabrica`'s own precedent). Also added
  `pynacl>=1.5` as a real, direct (not optional) dependency, since identity binding is now a core,
  always-on capability, not an opt-in extra. **Real, unexpected side effect worth knowing**:
  `civitas` only gained its own `py.typed` marker in a real, recent release — three
  `# type: ignore[misc]  # civitas lacks py.typed` comments (on `GovernedMessageBus`,
  `PolicyEvaluatorServer`, `RegistryServer`) were now genuinely unused and removed, which is what
  surfaced the `RegistryServer` bug above (a broad class-level ignore had been silently
  suppressing real attribute-type errors in the class body, not just the class definition line).
  Also added missing `mypy` override entries for `hvac`/`asyncpg` (no published stubs), found
  adjacent to this work. All 442+ tests (354 core + 108 contrib) pass, 3x stable, mypy and ruff
  clean on both packages.
- [x] **Close the `presidium_contrib.service.policy`/`.registry` 0%-coverage gap.** **Done
  2026-08-22.** Both files now at **100% coverage** (up from 0%) — 14 new tests: unit tests calling
  `handle_call()` directly (`test_service_policy.py`, `test_service_registry.py`) plus a real
  end-to-end integration suite through an actual `civitas.Runtime`/`Supervisor`
  (`tests/integration/test_service_mode_real_runtime.py`), including a dedicated regression test
  proving the `self._registry`/`AgentProcess._registry` collision fix (above) survives real
  Supervisor wiring, not just a static rename. **Found and fixed a second real, previously-hidden
  bug this same pass**: `PolicyEvaluatorServer._handle_load()` stored a raw string in
  `PolicyRule.decision` instead of converting it to the `PolicyDecision` enum —
  `CelPolicyEngine.evaluate()` accepted it silently, but `_handle_evaluate()`'s own
  `result.decision.value` then crashed with a real `AttributeError` on every non-default-ALLOW
  decision. 0% coverage had masked this entirely; caught immediately by the first real test that
  exercised a non-trivial policy outcome. `presidium-contrib` coverage: 71% → **82%**.
- [x] **Build M7 (Presidium Server) itself.** **Done 2026-08-22/23.** `check_grant()` over real
  REST+mTLS is shipped and now genuinely proven end to end (real handshake test, real published
  `civitas>=0.11.3` dependency, no workaround) -- the structural gap between "three separate
  pillars" and "one integrated platform" is closed for the `check_grant` path. Registry CRUD/
  approval/credential endpoints remain deferred (see M7 section below) -- not part of this item's
  own scope.
- [x] **Wire `GovernedModelProvider`/`GovernedToolProvider` to actually call a backend, not just
  check permission.** **Done 2026-08-22.** New `presidium.providers.civitas_adapters` module:
  `GovernedModelProviderAdapter`/`GovernedToolAdapter`, real structural implementations of
  `civitas.plugins.model.ModelProvider`/`civitas.plugins.tools.ToolProvider`, each constructed
  per-agent (`agent_name` bound at construction — the same, already-established pattern
  `civitas.process.AgentProcess.connect_mcp()` uses for `civitas-io/fabrica`'s own `MCPTool`, not
  a new one invented here). `GovernedRuntime` gained `model_for(agent_name, backend)`/
  `tool_for(agent_name, backend)` factory methods, mirroring Civitas's own `model_for()` naming.
  DENY still **raises** `PolicyDeniedError` (reusing `check()`'s existing behavior exactly) — a
  real, deliberate difference from `check_grant()`'s non-raising HTTP-boundary design, correct
  here because an in-process Python exception through the calling agent's own error boundary is
  the idiomatic Civitas convention, not a limitation to work around. 13 new tests, both new/
  touched modules at 100%/83% coverage (`runtime.py`'s remaining gap is pre-existing, unrelated).
  **Scope note, precise not overclaimed**: this solves "can `GovernedModelProvider`/
  `GovernedToolProvider` be a drop-in Civitas `ModelProvider`/`ToolProvider`" — it does **not**
  build the separate, larger `LLMGatewayBackend`/`ToolsGatewayBackend` *pluggable-vendor*
  abstraction from `docs/design/llm-gateway.md`/`mcp-gateway.md` (AgentGateway/LiteLLM/etc. as
  swappable backends) — that remains real, designed, not built (P1 above). `backend:
  ModelProvider`/`backend: ToolProvider` here can already be *any* object satisfying those real
  Civitas Protocols, including a future pluggable-vendor adapter, without further changes to
  these two new classes.

**Recommended sequence** (cheapest/most urgent first, not milestone order): ~~Ed25519 binding fix~~
→ ~~`civitas` PyPI pin~~ → ~~`service/*` test coverage~~ → ~~M7 network layer~~ →
~~`GovernedModelProvider`/`GovernedToolProvider` backend wiring~~. **All five done as of
2026-08-22.** Shipping a first real `presidium`/`presidium-contrib` PyPI release (see M5/P1 below)
can now genuinely be considered — the fictional-cryptographic-identity-claim blocker that made
releasing premature before is resolved. M5 itself (CLI, docs site, example applications) is still
real, separate work, not automatically unblocked by this alone.

### P1 — real, designed, necessary for genuine production-readiness, not immediately blocking

- [ ] `AgentGatewayClient` missing `list_tools()`/`call_tool()` — MCP/A2A governance is designed but
  not exercised end to end yet (LLM side works, tool side doesn't). Tracked under M7.
- [ ] Build `presidium-contrib[spiffe]` (real SPIRE SVIDs) — the "full" version of the P0 Ed25519
  item above, once the basic binding is fixed. Tracked under M7.
- [ ] LiteLLM adapter + stub adapters (Kong/Portkey/Cloudflare AI Gateway/Helicone/TrueFoundry) —
  real market flexibility; AgentGateway already covers the reference path so this isn't urgent.
- [ ] **Default-deny for `CelPolicyEngine`'s no-rule-matched case — direction decided, implementation
  deliberately deferred, not a style nit.** Today, no rule matching a stage silently defaults to
  `ALLOW`. **Explicit real-world preference recorded 2026-08-22**: default DENY over default ALLOW
  is the right posture, even at real UX cost, because it reduces blast radius — stated directly,
  not inferred. **A real implementation attempt was made and reverted the same session**, on
  purpose, once its actual blast radius became concrete: flipping `CelPolicyEngine`'s no-match
  return from `ALLOW`/`"All policies passed"` to `DENY`/`HARD` broke **24 existing tests** across
  `test_cel.py`, `test_governed_tool.py`, `test_governed_model.py`, and
  `test_governed_runtime.py` — because Presidium's whole existing test suite (and, implicitly, its
  whole current policy-authoring model) assumes an implicit allow-by-default; almost none of the
  existing example/test policies declare an explicit terminal ALLOW rule. This is not a small,
  local fix — it is a real change to how every Presidium deployment must author policies (an
  allowlist model: explicit ALLOW + explicit DENY + explicit REQUIRE_APPROVAL, nothing implicit),
  and needs its own dedicated design pass, not a one-line patch. **Real, scoped follow-up work
  needed before implementing**: (1) decide whether this is a hard, unconditional default-deny
  (matches the stated preference most directly) or a `default_decision`/`strict` constructor
  parameter (safer migration path, more code); (2) update every existing example/test policy set
  to add an explicit terminal ALLOW rule wherever one was previously implicit; (3) update
  `docs/design/policy-engine.md`/`docs/quickstart.md`/any tutorial content that currently shows a
  policy set without a terminal allow rule, since those examples would now deny everything;
  (4) decide the exact `reason`/`policy_name` shape for the new default-deny `PolicyResult`
  (already drafted once: `reason="No policy rule matched this request (fail-closed default — no
  implicit allow)"`, worth reusing). Revisit as its own, dedicated piece of work — not bundled into
  M7 or any other milestone by default.
- [x] **Trust ceiling propagation — DONE, real, shipped (2026-08-22).** Was: a real,
  currently-exploitable "trust washing" gap surfaced by a direct comparison against Microsoft's
  Agent Governance Toolkit (`microsoft/agent-governance-toolkit`)'s `AGENTMESH-IDENTITY-TRUST-1.0`
  spec. `AgentRecord.trust_ceiling: float | None` + `LinearTrustScore(ceiling=...)` (clamps
  `.value`'s getter, `HUMAN_OVERRIDE`/`set_value()` deliberately still respects it — a hard
  boundary, not a bypass; an admin who wants to grant more must explicitly raise
  `trust_ceiling` itself). New `presidium.lineage.compute_child_ceiling()`
  (`min(requested or 1.0, parent.trust_ceiling or 1.0, parent.trust_value)`, naturally transitive
  across a multi-hop chain, a one-time snapshot at registration — not continuously re-derived).
  Enforced inside `register()`/`add_grant()` on **all three registry backends**
  (`InMemoryRegistry`, `SqliteRegistry`, `PostgresAgentRegistry`) — defense in depth, not an
  opt-in helper a caller could skip. A dangling `parent_agent_id` now fails closed
  (`UnresolvableParentError`) rather than being silently ignored, since silently ignoring it would
  reopen the exact bypass this closes.
- [x] **Monotonic capability narrowing on delegation/spawn — DONE, real, shipped (2026-08-22).**
  Same source comparison. AGT requires every delegated/spawned agent's granted capabilities to be
  a strict subset of its delegator's own, plus a hard delegation-depth limit (AGT's default: 10,
  reused as-is). New `presidium.lineage.validate_grant_narrowing()` — checks the union of
  (resource, action) pairs is a subset of the parent's (Presidium's grant model has no wildcard
  concept, so AGT's "reject wildcard delegation" rule is moot here; deliberately does NOT compare
  `scope`/`condition`/`expires_at` narrowing — proving a CEL condition string is "narrower" is
  undecidable in general, a documented non-goal). Raises `GrantEscalationError` rather than
  silently narrowing, since unlike trust, a grant is binary and can't be safely auto-clamped.
  New `presidium.lineage.compute_child_depth()` + `AgentRecord.depth`, stored/inherited at
  registration (not chain-walked), `max_delegation_depth` configurable per registry instance.
  Enforced in `register()` **and** `add_grant()` (an escalation attempt can't just be deferred to
  a later `add_grant()` call), across all three registry backends. 60+ new tests (pure-function
  unit tests in `test_lineage.py`, registry-level integration tests parametrized over
  `InMemoryRegistry`/`SqliteRegistry`, mock-based `PostgresAgentRegistry` tests proving the exact
  same shared `presidium.lineage` functions are used, not a divergent reimplementation).
  All 439 `presidium` + 158 `presidium-contrib` tests pass, 3x stable, `ruff`/`mypy --strict`
  clean. **Real, deliberate scope note**: there is still no real "spawn" composition anywhere in
  the whole system (Civitas's `Runtime.spawn()` doesn't call Presidium; Fabrica's
  `CivitasBridge.request_supervision()` is a pass-through, not called by Fabrica's own managers in
  v1) — this closes the registry-level hole so that whichever real orchestrator eventually gets
  built inherits safety by default, not a live exploit against a running feature.
- [ ] Compose the three MCP governance primitives (`PIIDetector`, `PoisoningDetector`, redaction)
  into one real pipeline — today callers must wire all three in themselves. **Real, richer
  candidates found in the same AGT comparison**, worth evaluating alongside this: message signing
  with replay protection, session tokens with TTL, sliding-window rate limiting (already flagged
  above under M7), and CVE-feed integration (OSV API) against MCP servers in active use — AGT's
  `MCP-SECURITY-GATEWAY-1.0` spec covers all of these; none are committed here yet, listed as
  real candidates to evaluate, not a plan to copy wholesale.
- [ ] Fix `AGENTS.md` documenting extras (`litellm`, `kong`, etc.) that don't exist in
  `pyproject.toml` yet — cheap doc fix once the adapters above land.
- [ ] M4: Autonomy Progression (see below) — real, well-specified, but Presidium is genuinely
  usable without it (trust tiers work fine statically in the meantime).
- [ ] M5: SDK + CLI, docs site, example applications. **The "real first PyPI release + git tag"
  half of this item is DONE** (`presidium` v0.2.1, `presidium-contrib` v0.2.0, both live on PyPI,
  real git tags/GitHub Releases) — the CLI/docs-site/examples half remains, now genuinely
  unblocked since every P0 item above is true.
- [ ] M8: Performance Research — correctly sequenced after M7, not before (see M8 below).

### P2 — deferred by design, commercial, or dependent on things outside our control

- M6: Cloud — explicitly commercial, multi-tenant SaaS; not core-completeness.
- Inbound A2A exposure — needs Civitas to gain an A2A *server* role first; a Civitas-side feature,
  not Presidium's to unblock alone.
- RFC-002 (multi-dimensional evaluation) — already labeled "Future Investigation," research-first,
  no concrete plan yet.
- Deferred adapters (`CedarPolicyEngine`, `TemporalApprovalService`) — no unique capability gap;
  CEL+OPA and Slack/Webhook already cover the space.

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

**Priority: P1** — real and well-specified, but Presidium is genuinely usable without it (trust
tiers work fine statically in the meantime). See "Implementation Priority" above.

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

**Priority: P1.** The gating condition (every P0 item true, no fictional cryptographic-identity
claim) is now genuinely met -- `presidium` v0.2.1/`presidium-contrib` v0.2.0 are real, live PyPI
releases with a real Ed25519 identity binding and a real, proven mTLS handshake behind them. What
remains here is the CLI/docs-site/examples work specifically, not the release itself.

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

**Priority: P2** — explicitly commercial, multi-tenant SaaS; not core-completeness.

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

**Priority: P0** — the single structural blocker to the three-pillar platform working end to end.
See "Implementation Priority" above for the full P0/P1 breakdown of this milestone's own items.

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

**Full design finalized 2026-08-22** — [presidium-server-requirements.md](../design/presidium-server-requirements.md)
and [presidium-server.md](../design/presidium-server.md). The summary below is kept for history;
the two design docs are now the authoritative source for exactly what gets built.

**Builds on real, existing work — this is a transport skin, not a rewrite:**

- Reuses `GovernedRuntime`'s existing composition (policy engine, registry, approval,
  credentials, trust) as the implementation behind the one real endpoint — no new governance
  logic.
- **Finalized design decision, superseding this bullet's original framing**: does **not** recompose
  `PolicyEvaluatorServer`/`RegistryServer`'s separate GenServer call protocols for `check_grant` —
  that would mean re-deriving orchestration (lookup → evaluate → approval) that already exists,
  correctly, as `GovernedRuntime`'s own object graph. Instead, a new, thin `PresidiumGatewayAgent`
  wraps a `GovernedRuntime` directly. Those two GenServers remain valid for a later, genuinely
  distributed deployment topology — not this one. See `presidium-server.md`'s own "Architecture"
  section for the full reasoning.
- Implements the AAA architecture already designed in
  [RFC-001](../rfcs/001-presidium-scope.md#aaa-architecture-holistic-view) and
  [`docs/research/aaa-patterns.md`](../research/aaa-patterns.md) — this milestone is "build the
  server RFC-001 already describes," not a new architecture decision.

**Major real finding, 2026-08-22 — reuse `civitas.gateway.HTTPGateway` directly, don't build a new
server framework.** A direct read of `python-civitas`'s own source (not assumed) found it already
ships a mature, well-tested (91-100% coverage across its submodules), production-grade HTTP/gRPC/
HTTP3 gateway with real mTLS (`GatewayConfig.tls_cert`/`tls_key`/`tls_ca_cert`/`client_cert_mode`,
`civitas/gateway/mtls.py`, 98% covered) and real JWT bearer auth (`civitas/gateway/jwt_auth.py`,
100% covered) already built in. Critically, `HTTPGateway` is **transport-agnostic and
declarative**: a route is just `{"method": "POST", "path": "/v1/...", "agent": "<name>", "mode":
"call"}`, dispatched onto the Civitas bus via `GatewayDispatcher` to *any* named agent — not
limited to a fixed set of built-in routes. Since `PolicyEvaluatorServer`/`RegistryServer` are
**already real `AgentProcess`/`GenServer` subclasses** (M3, shipped), most of M7's own "REST
endpoints" and "mTLS" requirements below could be satisfied by **registering these agents behind
an `HTTPGateway` with a routes/`GatewayConfig` manifest**, not by building a new REST+mTLS server
from scratch. This substantially de-risks and likely de-scopes M7 — see `examples/http_gateway.py`
and `examples/gateway_auth.py` in `python-civitas` for the exact reusable pattern. Re-verify this
assumption early in implementation (confirm `HTTPGateway`'s auth middleware composes cleanly with
Presidium's own grant/policy checks, not just transport-level authentication) before committing
to it fully, but treat "build a new server" as the fallback, not the default.

**Requirements:**

- [x] Close the existing test-coverage gap: `presidium_contrib.service.policy`/`.registry` (the
  GenServers this milestone wraps). **Done 2026-08-22** — see "Implementation Priority" → P0
  above for the full write-up (both files now 100%, a real second bug found and fixed in the
  process).
- [x] **Wire up the Ed25519 identity binding that M2 already documents as done but never actually
  implemented.** **Done 2026-08-22** — see the full write-up under "Implementation Priority" → P0
  above. `GovernedRuntime.start()` now binds a real, persistent `AgentIdentity` per agent;
  `AgentRegistry` gained a real `verify_signature()`. **Still open, not done by this fix**: the
  actual mTLS wiring below (this item only unblocks it by making the underlying key real).
- [x] **(P0)** Design docs: `docs/design/presidium-server-requirements.md` + `presidium-server.md`.
  **Done 2026-08-22** — full design walkthrough, real decisions recorded (Option A architecture
  reusing `civitas.gateway.HTTPGateway`, the `check_grant()` action-mapping algorithm, the new
  non-blocking `GovernedToolProvider.check_grant()` method, mTLS via a real private CA rather than
  waiting on SPIRE, a minimal explicit `/health` route). Ready for implementation review.
- [x] **(P0)** Package shape decided: **`presidium_contrib.server`**, a new module in
  `presidium-contrib` (extra: `presidium-contrib[server]`, needs `civitas[http]`) — settles the
  three-option decision below in favor of the `civitas-gateway`-reuse approach, formalized as a
  real module rather than a separate standalone package.
- [x] **(P0)** Implement `PresidiumGatewayAgent` and `GovernedToolProvider.check_grant()`.
  **Done 2026-08-22.** `POST /v1/check_grant` + `GET /health` only in this first cut — registry
  CRUD, approval request/list/decide, and credential resolution remain designed (see
  `presidium-server.md`'s own "Deferred" section) but explicitly out of scope for now. **A real,
  second implementation-time correction found and fixed**: the design's original
  `payload_extra`-based single-agent dispatch doesn't work —
  `civitas.gateway.router.RouteTable.from_config()` never populates `payload_extra` for ordinary,
  user-declared routes (confirmed live: a real `GET /health` returned `400 {"error": "Unknown
  operation: None"}`). Fixed with one real agent per route (`PresidiumGatewayAgent` for
  `check_grant`, a new `HealthCheckAgent` for `/health`) instead — simpler, and correctly matches
  the real API. 39 new tests (unit + a real end-to-end suite through an actual `HTTPGateway` and
  real `httpx` requests over real HTTP), both new modules at 100% coverage.
- [ ] **(deferred, tracked not forgotten)** Registry CRUD + grant management, approval
  request/list/decide, credential resolution over the network — real, designed intents
  (`presidium-server.md`'s own "Deferred" section sketches how each would extend the same
  `PresidiumGatewayAgent` pattern), not built until something concretely needs them.
- [ ] **(real, honest gap, not silently claimed done)** `scope` (FR-1.4) is not yet threaded
  through to `ActionRequest.parameters` — CEL policies cannot yet reference `request.parameters`
  from a `check_grant` call. Small, real follow-up.
- [x] **(P0)** **Must satisfy `civitas-io/fabrica`'s `PresidiumClient.check_grant()` contract
  exactly**: synchronous REST, `agent_id` + `action` + `scope` in,
  `GrantResult(decision, reason, approval_context)` out (confirmed directly against
  `civitas-io/fabrica/docs/contracts/managers.md`) — shipped, minus the `scope` gap noted directly
  above.
- [x] **(P0)** Preserve fail-closed semantics across the network boundary: an unreachable or
  erroring server must be something the *client* can safely treat as `deny` without the server
  needing to do anything special — confirmed shipped: `PresidiumGatewayAgent` never raises for a
  missing field, an unresolvable agent, or any policy decision; a real end-to-end test proves a
  `200` (never a `5xx`) for every one of these cases over real HTTP.
- [x] **(P0)** mTLS at the transport boundary, not bearer tokens/API keys as the primary
  mechanism. **Config-level wiring done earlier (`require_mtls=True` default,
  `civitas.gateway.mtls.require_client_cert`); a real handshake test done 2026-08-23 found this
  went further than "untested" — the currently-published `civitas` (>=0.11.0) never actually
  delivered a real client certificate to the ASGI app at all, so every request, valid or not, got
  `401`.** Root cause: a known, tracked, upstream gap (uvicorn never populates the ASGI TLS
  extension) — `civitas-io/python-civitas#25`'s `direct`-mode half, explicitly left broken by that
  repo's own earlier `proxy_header` fix. Reported, designed, and fixed upstream the same day
  (`civitas-io/python-civitas` commit `8d72084`, `docs/design/gateway-http-mtls-direct.md`) — a
  new `TlsAwareHttpToolsProtocol` reads the real peer certificate straight off the TLS transport.
  Verified end to end against Presidium's own real mTLS test suite via a local, uncommitted
  editable install of the fixed `python-civitas` (all 4 handshake scenarios passed) — then
  reverted to the published dependency, since the fix isn't in a tagged `civitas` release yet.
  **Presidium's own test
  (`packages/presidium-contrib/tests/integration/test_presidium_server_mtls.py`) marked the two
  scenarios that needed the fix `xfail(strict=True)`** until a real release existed. **Done for
  real, 2026-08-23**: the fix shipped as `civitas` v0.11.2 (immediately followed by v0.11.3, a
  same-day patch after v0.11.2's own release verification caught a real, live packaging bug —
  `import civitas` failed entirely; see that repo's own CHANGELOG). Bumped this package's pin to
  `civitas>=0.11.3`, removed both `xfail` markers — all 4 handshake scenarios now pass for real
  against the real, published dependency, no local override, no workaround. 439 `presidium` + 162
  `presidium-contrib` tests pass, 3x stable, `ruff`/`mypy --strict` clean.
- [ ] **(P1)** Build `presidium-contrib[spiffe]` — real SPIRE-issued X.509-SVIDs, auto-rotation,
  cross-deployment federation via trust domain bundles. **Real, pre-existing doc drift this
  resolves**: `docs/design/agent-registry.md` already describes this extra as an "M3+ upgrade
  path" but it **does not exist anywhere in the real codebase** — no module, no pyproject
  extra, not even a stub. This milestone is where it would actually need to get built. Sequenced
  after the basic Ed25519 binding above, not instead of it.
- [ ] **(P1)** Rate limiting / backpressure at the network boundary — a real concern for a shared
  network service that doesn't exist for an in-process library call

**Deliverable:** A real, self-hostable Presidium server process, reachable over REST+mTLS by
any authenticated external client (Civitas-based or not) — the concrete prerequisite that
unblocks Fabrica's `PresidiumClient` real implementation, and the technical foundation M6's
"Presidium Cloud" would eventually run as a managed, multi-tenant version of.

---

## M8: Performance Research — Rust vs. Python at the governance hot path

**Priority: P1, and only after M7 ships** — this only becomes load-bearing once Presidium is a
real multi-tenant network service. See "Implementation Priority" above.

**Goal:** A research milestone, not a rewrite commitment. Answer, with real measured evidence,
whether any part of Presidium's request-path hot loop needs to move off pure Python — and if so,
which part, and how — before it becomes a real production bottleneck rather than after.

**Trigger:** A direct, evidence-based comparison already exists one layer down: AgentGateway
(Rust) vs. LiteLLM Proxy (pure Python) is cited in `docs/design/llm-gateway.md`'s own adapter
table as a real, named trade-off (LiteLLM needs Postgres+Redis to scale where AgentGateway is a
single binary) — and LiteLLM itself is reportedly moving toward a Rust rewrite for exactly this
reason. Presidium's own policy-evaluation hot path has the same structural shape as LiteLLM's:
pure Python, in the synchronous critical path of every governed action, GIL-bound within a
process. Worth checking with real numbers before assuming either "it's fine" or "it needs Rust."

**Real, measured baseline established while scoping this (not a guess):**

- `CelPolicyEngine.evaluate()` (`cel-python`/`celpy`, confirmed pure Python — a `lark`-based
  tree-walking interpreter, no Rust/C core): **~88µs per evaluation, ~11,400 evaluations/sec on
  one core**, with 20 loaded rules, first-match-wins. This is the dominant cost in a `check()`
  call — registry lookups are ~10x cheaper (see below) — and scales with rule count, since
  first-match-wins means a request that matches no rule (the common ALLOW case) evaluates every
  loaded rule for that stage.
- `InMemoryRegistry.lookup()` (deep-copy snapshot semantics): **~9µs, ~112,000 lookups/sec on one
  core.** Not the bottleneck; CEL evaluation is.
- **The real constraint is the GIL, not raw per-call cost.** ~88µs in isolation is not
  catastrophic — the problem is that Python's GIL means this ceiling does not rise with more CPU
  cores *within a single process*; scaling past it today means horizontal replicas, not vertical
  throughput. This is exactly the shape of AgentGateway's structural advantage over LiteLLM.

**Why this isn't urgent yet, and why it will become real precisely at M7:** In today's
library-mode usage, this cost is paid once per tool/LLM call inside an agent's own async loop —
negligible next to LLM call latencies (milliseconds vs. seconds), and concurrency is naturally
bounded by how many agents one Civitas runtime hosts. **It becomes a real, load-bearing question
specifically once M7 exists** — a shared, multi-tenant, externally-callable service is the first
place Presidium has the same concurrent-request profile AgentGateway/LiteLLM actually have.
Sequenced after M7 for this reason, not because it's unimportant.

**Research questions, not answers pre-decided:**

- [ ] Benchmark realistic Presidium call paths (not isolated micro-benchmarks) under real
  concurrent load against an actual M7 server, once it exists — rule-set sizes and concurrency
  levels drawn from a real or realistic deployment, not synthetic worst cases
- [ ] Option A — horizontal scaling only (multiple `presidium-server` OS processes/replicas
  behind a load balancer), zero code changes, cheapest engineering cost. Does this alone clear a
  realistic target QPS?
- [ ] Option B — free-threaded CPython (PEP 703, the `3.13t`/`3.14t` builds). Presidium already
  targets 3.12/3.13/3.14. Does removing the GIL alone close the gap without introducing Rust at
  all? A real, current option that didn't exist when AgentGateway/LiteLLM made their original
  language choices.
- [ ] Option C — a Rust-backed CEL evaluator behind the same `PolicyEngine` Protocol (e.g. a
  `cel-rust` + PyO3 binding), keeping the rest of `presidium` pure Python. Matches this
  project's own interface-library discipline: swap the implementation, not the Protocol.
- [ ] Option D — a fuller Rust rewrite of the M7 network-facing layer specifically (the part
  structurally equivalent to AgentGateway), leaving `presidium`/`presidium-contrib` as pure-Python
  libraries for embedded/library-mode use. Most invasive; only worth it if A-C don't clear the bar.
- [ ] MCP governance's regex-based scanning (`PIIDetector`, `PoisoningDetector`, redaction) —
  CPU-bound string processing over potentially large tool outputs, a second real GIL-bound cost
  center worth benchmarking alongside policy evaluation, not assumed fine by proximity.

**Deliberately not decided here, per this project's own "ship the default, revisit only with
evidence" discipline** (the same discipline that shipped `fabrica`'s retriever as pure Python v1
rather than pre-optimizing in Rust): no component gets rewritten in Rust as part of this
milestone. The deliverable is a design doc with real numbers and a recommendation, not code.

**Deliverable:** `docs/design/performance-research.md` — real benchmark results against an actual
M7 deployment, a clear recommendation (which option, if any, and why), and either a follow-up
implementation milestone or an explicit "pure Python is sufficient, revisit if X changes" call.

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
| M8: Performance Research (Rust vs. Python) | After M7 | Planning |
