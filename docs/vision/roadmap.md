# Roadmap

> Phase-based development plan for Presidium.

## Philosophy

Documentation-driven development. Design docs and RFCs are written and reviewed before implementation begins. Each milestone (M) represents a coherent, shippable increment.

---

## M1: Foundation (Current)

**Goal:** Establish project identity, architecture, and documentation.

- [x] Repository setup (monorepo, uv workspace, CI/CD)
- [x] AGENTS.md
- [x] Vision documents (manifesto, positioning, roadmap)
- [x] Architecture overview and package map
- [x] Competitive research archive
- [ ] RFC-001: Presidium scope and boundaries
- [ ] Design doc: Agent Registry
- [ ] Design doc: Policy Engine
- [ ] Community feedback on architecture

**Deliverable:** Complete documentation. No code.

---

## M2: Registry + Policy

**Goal:** Core governance primitives — know who your agents are, control what they can do.

- [ ] `presidium-registry` package
  - Agent identity (name, version, capabilities)
  - Capability registration and lookup
  - Trust score tracking
  - Lifecycle state tracking
- [ ] `presidium-policy` package
  - YAML policy definitions
  - Policy evaluator
  - Supervisor integration (policies as constraints)
  - Action-level enforcement (allow, deny, require-approval)
- [ ] Integration tests with Civitas runtime
- [ ] Getting started guide

**Deliverable:** `pip install presidium-registry presidium-policy`

---

## M3: Gateways

**Goal:** Govern access to LLMs and tools.

- [ ] `presidium-llm-gateway` package
  - LLM provider routing (Anthropic, OpenAI, Gemini, etc.)
  - Per-agent rate limiting
  - Cost tracking and budget enforcement
  - Content filtering hooks
- [ ] `presidium-mcp-gateway` package
  - Tool access control lists
  - Tool poisoning detection
  - Credential redaction
  - Audit logging for tool calls
- [ ] Design doc: HTTP Gateway (deferred to M4)

**Deliverable:** `pip install presidium-llm-gateway presidium-mcp-gateway`

---

## M4: Eval + Observability Integration

**Goal:** Governance-aware evaluation and external platform integration.

- [ ] `presidium-eval` package
  - Governance evaluation metrics (policy compliance rate, trust drift, etc.)
  - Scoring framework
  - Fiddler exporter
  - Arize exporter
  - Langfuse exporter
  - Custom exporter protocol
- [ ] OTEL enrichment (governance spans alongside Civitas runtime spans)
- [ ] Dashboard design (TUI or web — TBD)

**Deliverable:** `pip install presidium-eval`

---

## M5: Unified SDK + CLI

**Goal:** One package, one install, complete experience.

- [ ] `presidium-sdk` package
  - Unified imports: `from presidium import GovernedAgent, Policy, Registry`
  - YAML topology integration (extend Civitas topology with governance config)
  - CLI: `presidium run`, `presidium policy validate`, `presidium registry list`
- [ ] Comprehensive documentation site (MkDocs)
- [ ] Example applications (3-5 real-world scenarios)
- [ ] v0.1.0 release

**Deliverable:** `pip install presidium`

---

## M6: Cloud + Monetization (Future)

**Goal:** Managed service and enterprise features.

- [ ] Presidium Cloud (managed runtime + governance)
- [ ] Enterprise features (SSO, RBAC, SOC 2 compliance)
- [ ] Compliance automation (EU AI Act, NIST AI RMF mapping)
- [ ] Multi-region deployment
- [ ] SLA guarantees
- [ ] Pricing tiers (Free → Starter → Pro → Enterprise)

**Deliverable:** Commercial offering.

---

## Timeline

These are aspirational, not commitments. Adjusted based on community feedback and contributor availability.

| Milestone | Target | Status |
|---|---|---|
| M1: Foundation | Q2 2026 | In progress |
| M2: Registry + Policy | Q3 2026 | Planning |
| M3: Gateways | Q3-Q4 2026 | Planning |
| M4: Eval | Q4 2026 | Planning |
| M5: SDK | Q1 2027 | Planning |
| M6: Cloud | 2027+ | Future |
