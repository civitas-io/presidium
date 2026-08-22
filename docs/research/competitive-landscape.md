# Competitive Landscape

> Analysis of the agent infrastructure market as of April 2026.
> Source: Research conducted across GitHub, Microsoft Tech Community, Work-Bench, and industry reports.

## The Agent Runtime Stack

Work-Bench (NYC, $160M enterprise VC fund) published "The Rise of the Agent Runtime" (Feb 2026), identifying four pillars:

| Pillar | What It Does | Key Players |
|---|---|---|
| **Execute** | Sandboxes, skills, safe action | E2B, Civitas, Temporal |
| **Constrain** | Permissions, identity, guardrails | AGT, Fiddler, NeMo Guardrails |
| **Observe** | Monitoring, tracing | Fiddler, Arize, Langfuse, Datadog |
| **Improve** | Feedback loops, learning | LangSmith, Braintrust |

**Presidium's positioning:** Covers Execute (via Civitas) + Constrain natively. Generates signals for Observe + Improve.

---

## Detailed Competitor Analysis

### Temporal ($5B valuation, $300M Series D, Feb 2026)

**What it is:** Durable execution platform — workflow replay, fault tolerance, state persistence.

- 380% YoY revenue growth
- 20M+ installs/month, 9.1T lifetime action executions
- Customers: OpenAI, Netflix, Snap, JPMorgan Chase
- a16z partner Sarah Wang: "Reliability is a gating factor... Temporal is the execution layer"

**Strengths:** Proven at massive scale. Polyglot (Go, Java, Python, TypeScript). JVM-native.
**Gaps:** No governance. No agent-native primitives (no supervision trees, no message passing). Requires Temporal cluster infrastructure.

**Relevance to Presidium:** Same layer (runtime) but different model. Temporal = workflow replay. Civitas/Presidium = actor model + supervision. Not direct competitors — different architectural philosophy.

### Microsoft Agent Governance Toolkit

> **Re-verified directly against the real repo, 2026-08-22** (`microsoft/agent-governance-toolkit`,
> v4.1.0, public preview) — cloned and read, not re-summarized from memory. Corrects and extends
> the entries below; does not replace this section's own earlier real research.

**What it is:** Multi-language governance toolkit for AI agents. Now 9 packages consolidated into
**5 top-level PyPI distributions** (`-core`, `-runtime`, `-sre`, `-cli`, `[full]` meta-package) plus
TypeScript/.NET/Rust/Go SDKs. Covers policy enforcement, zero-trust identity, privilege rings,
SLOs, compliance mapping (OWASP Agentic Top 10, NIST AI RMF, EU AI Act, SOC 2), and framework
adapters. **Real, substantial maturity confirmed directly**: 10 formal RFC 2119 specifications
backed by **992 conformance tests**, 29 ADRs. The policy layer (**ACS — Agent Control
Specification**) is a stateless, deterministic, fail-closed **Rust core** with a Python SDK built
via maturin — not the pure-Python model Presidium's `CelPolicyEngine` uses.

**Strengths:** Comprehensive scope. Microsoft backing and enterprise credibility. Multi-language
SDKs. Framework-agnostic (LangChain, CrewAI, AutoGen, Semantic Kernel, Microsoft Agent Framework,
Google ADK, and others). Own honest "Known Limitations" doc naming real gaps (a composability gap
where two individually-permitted actions form an exfiltration path; audit logs record attempts,
not outcomes; a knowledge-governance gap around RAG provenance) rather than overclaiming.

**Gaps:**
- No runtime — governance middleware only, not an actor-model runtime. Their own README states
  enforcement happens "at the application middleware layer, not the OS kernel level," and
  explicitly recommends running each agent in a separate container for OS-level isolation —
  something they don't build themselves. (`civitas-io/fabrica` already does, with real
  hardware-validated tiers — see `projects/fabrica.md`.)
- Significant complexity — 9 packages, 5 distributions, multi-language monorepo.
- **"Privilege rings partially unimplemented" (prior entry): not re-verified this pass** —
  don't treat as still-current without checking the real v4.1.0 source directly.

**Two real, concrete gaps this comparison surfaced in Presidium itself, not just in AGT** (now
tracked in `docs/vision/roadmap.md`'s Implementation Priority → P1): no trust ceiling propagation
(AGT's `AGENTMESH-IDENTITY-TRUST-1.0` spec prevents "trust washing" — repeatedly spawning fresh
identities to reset a degraded trust score — via a `trust_ceiling` enforced across delegation
chains; Presidium has no equivalent), and no enforcement of monotonic capability narrowing on
delegation/spawn (a child agent can currently end up with *more* grants than its parent).

**Presidium's differentiators:**

| Presidium | Microsoft AGT |
|---|---|
| Governance native to the runtime — supervisor constraints, not interceptors | Application middleware layer — wraps existing agents |
| Transport-layer enforcement via `GovernedMessageBus` — every message routed through Civitas | Explicit whole-turn `input`/`output` intervention points bracket the full agent loop (a genuinely different, not strictly worse, model — see below) |
| OTP supervision as structural trust root | Policy-defined trust hierarchy + a formal agent-to-agent trust handshake protocol (IATP) Presidium has no equivalent of |
| Mid-flight behavioral correction via EvalLoop + CorrectionSignal | Post-hoc evaluation |
| Single Python-native package, pure-Python CEL engine (`cel-python`) | Multi-language, multi-package; Rust-core policy engine (ACS) |

**Where AGT is genuinely more built out, worth learning from directly:**
- MCP governance: message signing (HMAC + replay protection), session tokens with TTL, sliding-
  window rate limiting, per-server TLS/auth enforcement, CVE feed integration via the OSV API,
  cross-server confused-deputy detection — all real gaps versus Presidium's current `mcp_gateway`
  (PII detection, tool-poisoning hash fingerprinting, credential redaction only).
- ACS's `transform` verdict type unifies "decide" and "sanitize" into one policy output, instead
  of Presidium's separate redaction/masking utilities layered on top of a decision.
- Formal RFC 2119 specs paired with dedicated conformance test suites, as a distinct discipline
  from test coverage percentage — worth considering as Presidium's own design docs mature.

**Where Presidium/the broader civitas-io ecosystem may already be ahead — stated with real
evidence, not assumed:** `civitas-io/tessera`'s agent-blind credential model (a secret never
enters agent-observable memory at all) is arguably stronger than AGT's own admitted "Credential
Persistence Gap" (AGT tracks and revokes at boundaries, but doesn't prevent exposure in the first
place). `civitas-io/fabrica`'s three real, hardware-validated sandbox tiers directly answer the
OS-level isolation gap AGT names as external to itself.

### Fiddler ($100M total funding, Series C Jan 2026)

**What it is:** AI observability and security platform — "The Control Plane for AI Agents."

- Founded 2018, pivoted from ML observability to agentic AI
- Fortune 500 customers, 4x revenue growth in 18 months
- SOC 2 Type 2, HIPAA compliant
- Investors: Lightspeed, Lux Capital, Insight Partners, a16z (earlier rounds)

**Product:**
- Trust Models: Purpose-built scoring models (<100ms latency)
- Guardrails: Real-time input/output moderation
- Agentic Observability: Application → session → agent → trace → span hierarchy
- Compliance: Audit trails, governance dashboards

**Strengths:** Enterprise credibility. Fast guardrails (<100ms). Trust Models run in-environment (no data exposure). Strong framework integrations (LangGraph, Bedrock, Google ADK).
**Gaps:** No runtime. Watches agents, doesn't run them. SaaS model (agents send data to Fiddler).

**Relevance to Presidium:** Complementary. Presidium generates telemetry, Fiddler analyzes it. Different layers, different buyers.

### LangChain ($1.25B valuation, $125M Series B)

**What it is:** Agent framework + LangSmith observability platform.

- 90M monthly downloads, 35% of Fortune 500
- $12-16M ARR (mid-2025, growing)
- LangGraph for orchestration, LangSmith for observability

**Relevance:** Framework layer — below Presidium. LangGraph agents can run inside Civitas via adapters.

### CrewAI ($18M Series A, $3.2M ARR)

**What it is:** Multi-agent orchestration with roles/goals/crews.

**Relevance:** Framework layer. CrewAI crews can run inside Civitas (adapter planned).

### Inngest ($20M Series A) / Restate ($7M seed)

**What they are:** Durable execution for serverless/functions.

**Relevance:** Adjacent to Temporal. Lighter weight but less agent-specific.

---

## Market Summary

The landscape divides cleanly into layers:

| Layer | Funded | Gap |
|---|---|---|
| Frameworks | LangChain ($1.25B), CrewAI ($18M) | No fault tolerance, no governance |
| Runtime | Temporal ($5B), Inngest ($20M) | No governance |
| Governance | AGT (Microsoft), Fiddler ($100M) | No runtime |
| **Runtime + Governance** | **Nobody** | **Presidium's target** |
