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

**What it is:** Multi-language governance sidecar toolkit for AI agents. 9+ packages across
Python, TypeScript, .NET, Rust, and Go. Covers policy enforcement, zero-trust identity,
privilege rings, SLOs, compliance mapping (EU AI Act, NIST, HIPAA), and framework adapters.

**Strengths:** Comprehensive scope. Microsoft backing and enterprise credibility. Multi-language
SDKs. Framework-agnostic (LangChain, CrewAI, AutoGen, and others).

**Gaps:**
- No runtime — governance sidecar only. Enforcement depends on agents passing through the
  gateway; direct API calls and inter-agent messages that bypass the gateway are not covered.
- Significant complexity — 9+ packages, multi-language monorepo.
- Privilege rings (`agent-runtime`) are partially unimplemented in the current release.

**Presidium's differentiators:**

| Presidium | Microsoft AGT |
|---|---|
| Governance native to the runtime — supervisor constraints, not interceptors | External sidecar — wraps existing agents |
| Transport-layer enforcement — every message, regardless of routing path | Gateway-only coverage |
| OTP supervision as structural trust root | Policy-defined trust hierarchy |
| Mid-flight behavioral correction via EvalLoop + CorrectionSignal | Post-hoc evaluation |
| Single Python-native package | Multi-language, multi-package complexity |

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
