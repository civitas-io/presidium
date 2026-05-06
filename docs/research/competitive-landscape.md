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

### Microsoft Agent Governance Toolkit (AGT)

> **License:** MIT. Safe to study and draw inspiration from.
> **Reviewed:** 2026-05-06 via codebase analysis of microsoft/agent-governance-toolkit

**What it is:** Multi-language governance sidecar toolkit for AI agents. Python is the
reference implementation. 11 Python packages, 19 framework integrations, 5 language SDKs.

**Architecture (Python packages):**

| Package | What it does |
|---|---|
| `agent-os` | Policy engine (YAML, OPA Rego, Cedar), capability model, MCP gateway, intent declaration |
| `agent-mesh` | Zero-trust identity (DIDs, Ed25519), trust scoring, inter-agent protocol |
| `agent-runtime` | Privilege rings (Ring 0-3), saga orchestration — mostly stubs, empty src/ |
| `agent-sre` | SLOs, error budgets, circuit breakers, chaos engineering |
| `agent-compliance` | OWASP verification, red-team CLI, EU AI Act / NIST / HIPAA mapping |
| `agent-hypervisor` | Reversibility checker — classifies action blast radius |
| `agent-primitives` | Shared base types across all packages |

**Conceptual enforcement stack (innermost to outermost):**
1. Intent check — declared plan vs. actual action
2. Policy evaluation — YAML rules + OPA/Rego/Cedar (< 0.1 ms)
3. Constraint graph — DAG of agent-to-resource edges
4. MCP gateway — intercept, sanitize, rate-limit, HITL approval gate
5. Egress policy — domain allowlist on outbound connections
6. Execution ring enforcement — Ring 0 (orchestrator) to Ring 3 (sandboxed)
7. Audit log — JSONL, hash-chain architecture (cryptographic verification deferred)
8. Trust score update — 5-factor weighted model

**What's standard (already planned in Presidium):**
- YAML policy rules → ALLOW/DENY/AUDIT
- OPA/Rego/Cedar backends
- HITL escalation and approval workflows
- Audit logging
- Framework adapters
- Circuit breakers and SLO enforcement

**What's genuinely novel (see presidium/docs/design/agt-inspiration.md for detailed design notes):**

1. **Three-tier trust decomposition** — Identity / Authority / Liveness decay independently.
   Missed heartbeat = suspension (reversible), not revocation. Restoration via delegation chain hash.

2. **Intent declaration + drift detection** — Agents declare a plan upfront (`planned_actions`).
   Every actual tool call is checked against it. Unplanned actions trigger `DriftPolicy`
   (warn / block / re-declare). Catches goal-hijacking that per-action policy misses entirely.

3. **Context budget scheduler** — Token allocation modeled as OS CPU scheduling. Global pool,
   per-agent `ContextWindow`, 90%/10% lookup/reasoning split, typed Unix signals (SIGSTOP/SIGWARN),
   `BudgetExceeded` on overrun. The OTP analogue: `max_message_queue_len` for LLM context.

4. **Asymmetric policy-change propagation** — Tightening propagates immediately (412 on stale
   cache). Loosening respects TTL. Simple rule; prevents newly-revoked capabilities from being
   exercised by agents with stale policy caches.

5. **Named, configurable policy conflict resolution** — Four strategies: `DENY_OVERRIDES`,
   `ALLOW_OVERRIDES`, `PRIORITY_FIRST_MATCH`, `MOST_SPECIFIC_WINS`. Scope hierarchy:
   GLOBAL < TENANT < ORG < AGENT. Default: `DENY_OVERRIDES`.

6. **Folder-scoped hierarchical policy discovery** — `governance.yaml` files cascade down a
   directory tree. Parent `deny` rules cannot be overridden by children. Relevant for Presidium
   governing coding agents or CI/CD agents operating within a repo structure.

**What they reinvented that Civitas already has:**

AGT's `SupervisorHierarchy` states "Level 0 MUST be a deterministic (non-LLM) trust root"
and "escalation always terminates at the trust root." This is exactly what OTP supervision
trees enforce — the root supervisor is pure code, never an LLM process. Civitas gets this
for free and has had it since M1. They arrived here from the security direction; we arrived
from the reliability direction.

**AGT's acknowledged limitations (their own docs):**

- Doesn't govern reasoning — cannot intercept what happens inside an LLM call
- Cannot prevent knowledge leaks — a sequence of allowed actions can exfiltrate data one piece
  at a time through individually compliant queries
- `agent-runtime` privilege rings are partially aspirational — `src/` is empty in current repo
- No runtime — governance sidecar only; agents must exist in another framework

**Presidium's differentiators vs AGT:**

| Presidium | AGT |
|---|---|
| Governance native to the runtime — supervisor constraints, not interceptors | External sidecar — wraps existing agents |
| Transport-layer enforcement — every message, regardless of routing | Gateway-only — misses direct API calls and inter-agent messages that bypass gateway |
| OTP supervision as the trust root architecture | Reinvented supervision hierarchy from security first principles |
| EvalLoop + CorrectionSignal — mid-flight behavioral correction | Post-hoc evaluation only |
| Single Python-native package | 540K LOC across 5 languages |

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
