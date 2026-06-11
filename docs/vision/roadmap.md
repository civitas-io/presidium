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
- [ ] RFC-001: Presidium scope and boundaries
- [ ] Design doc: Agent Registry
- [ ] Design doc: Policy Engine
- [ ] Community feedback on architecture

**Deliverable:** Complete documentation. No code.

---

## M2: Core Interfaces + CEL Policy

**Goal:** All Protocol definitions in `presidium` core, plus working library-mode defaults. A developer can `pip install presidium` and have complete in-process governance.

- [ ] `presidium` package — all Protocol definitions:
  - `PolicyEngine` + `CelPolicyEngine` (in-process CEL evaluation via `cel-python`)
  - `AgentRegistry` + `InMemoryRegistry` / `SqliteRegistry`
  - `CredentialProvider` + `EnvCredentialProvider` / `FileCredentialProvider`
  - `TrustScorer` + `RuleBasedTrustScorer`
  - `ApprovalService` + `CallbackApprovalProvider` (stdin/callback for dev and test)
  - `AuditEnricher` + `InProcessAuditEnricher` (forwards to Civitas AuditSink)
  - `GovernedModelProvider` (in-process grant checks + rate limits)
  - `GovernedToolProvider` (in-process ACL checks)
- [ ] YAML topology integration — governance config extends Civitas topology files
- [ ] Integration tests with Civitas runtime
- [ ] Getting started guide

**Deliverable:** `pip install presidium` — complete library-mode governance. No sidecars, no infrastructure, no Rego.

---

## M3: Contrib Adapters + Reference Impls

**Goal:** `presidium-contrib` with adapters for existing products and reference implementations for novel components. Service mode for registry, policy, and trust scoring.

- [ ] `presidium-contrib` package
- [ ] Adapters (existing products):
  - `OPAPolicyEngine` — wraps OPA REST API for teams with existing Rego policies
  - `CedarPolicyEngine` — Cedar authorization model
  - `VaultCredentialProvider` — HashiCorp Vault KV engine with token renewal
  - `LiteLLMModelProvider` — routes through LiteLLM Proxy (100+ model support)
  - `SlackApprovalService` — approval requests via Slack with approve/deny buttons
  - `TemporalApprovalService` — human task workflows via Temporal
- [ ] Reference implementations (novel):
  - `PostgresAgentRegistry` — agent records, grant sets, trust score history in Postgres
  - `MCPGovernedToolProvider` — full MCP governance: ACL, tool poisoning detection, credential redaction
  - `LearningTrustScorer` — starts rule-based, learns from decision journal over time
- [ ] Service mode GenServer wrappers for registry, policy, and trust scoring
- [ ] `pip install presidium-contrib[opa]`, `presidium-contrib[vault]`, `presidium-contrib[slack]` extras

**Deliverable:** `pip install presidium-contrib[opa,vault,slack]`

---

## M4: Autonomy Progression

![Autonomy Progression](../assets/autonomy-progression.svg)

**Goal:** Close the feedback loop. Agents earn autonomy through demonstrated reliability.

- [ ] Decision journal GenServer — records (action, context, outcome, human_decision) for every HITL interaction
- [ ] Confidence-gated routing — automatic HITL when agent confidence falls below threshold
- [ ] Heuristic-to-learned policy progression — `RuleBasedTrustScorer` hands off to `LearningTrustScorer` as data accumulates
- [ ] Composite trust scoring — combines audit signals, eval scores, and human approval patterns
- [ ] Autonomy level API — agents can query their current autonomy level and what's needed to increase it
- [ ] Design doc: Autonomy Progression

**Deliverable:** Agents that start constrained and earn autonomy through behavior.

---

## M5: SDK + CLI

**Goal:** One package, one install, complete experience.

- [ ] `presidium` package unified imports: `from presidium import GovernedRuntime, Policy, AgentRecord`
- [ ] CLI: `presidium run`, `presidium policy validate`, `presidium registry list`, `presidium trust show`
- [ ] Comprehensive documentation site (MkDocs)
- [ ] Example applications (3-5 real-world scenarios)
- [ ] v0.1.0 release

**Deliverable:** `pip install presidium` — the full experience, documented and released.

---

## M6: Cloud

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
| M1: Foundation | Q2 2026 | Complete |
| M2: Core Interfaces + CEL Policy | Q3 2026 | Planning |
| M3: Contrib Adapters + Reference Impls | Q3-Q4 2026 | Planning |
| M4: Autonomy Progression | Q4 2026 | Planning |
| M5: SDK + CLI | Q1 2027 | Planning |
| M6: Cloud | 2027+ | Future |
