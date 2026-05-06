# Product Requirements Document
## Presidium
### *Runtime governance for autonomous AI systems — powered by Civitas*

**Version:** 0.1 (Draft)
**Date:** 2026-04-01
**Author:** Jeryn
**Status:** In progress

---

## 1. Problem Statement

### The Core Problem

Enterprises are deploying AI agents at scale. These agents send emails, execute code, manage calendars, spend budget, and act with delegated human authority — 24 hours a day, with minimal oversight.

The tooling to govern this has not kept up.

The market has observability platforms that tell you what happened after the fact. It has compliance dashboards that produce reports for auditors. What it does not have is **runtime governance** — controls embedded in the agent's execution path that determine what an agent can do, enforce policy before an action fires, and create a tamper-evident record of every decision.

This gap is not theoretical. Enterprises hit it in three concrete ways:

**Incident 1 — The Runaway Agent**
An agent tasked with "respond to customer emails" interprets its mandate broadly, escalates a refund beyond its approval limit, and commits the company to a $40,000 liability before anyone notices. There was no policy engine to enforce the approval ceiling. There was no blast radius control to pause the agent when spend anomalies appeared.

**Incident 2 — The Credential Inheritance Problem**
An agent operating with an executive's delegated credentials is exposed to a prompt injection attack via a malicious calendar invite. The attack instructs the agent to exfiltrate emails to an external address. The agent complies — it has the credentials to do so. No per-agent identity, no scoped permissions, no audit trail tied to the agent's identity rather than the human's.

**Incident 3 — The Compliance Gap**
A financial services firm deploys a research agent to assist analysts. EU AI Act Article 13 requires transparency and logging for high-risk AI systems. The firm's audit log shows HTTP calls and model responses — not the agent's decision chain, which policy constraints were active, why a tool was invoked, or which human approved a sensitive query. The audit fails.

### Why Existing Tools Don't Solve This

| Tool category | What it provides | What's missing |
|---|---|---|
| AI observability (generic) | Latency, errors, traces | Agent identity, decision context, cost per agent, behavioral drift |
| Compliance dashboards | Policy documents, risk registers | Enforcement — policies exist on paper, not in the execution path |
| Cloud provider governance | Platform-level controls | Conflict of interest; only covers their own models and services |
| Agent frameworks | Agent orchestration | No governance primitives at all |
| **Amazon Bedrock AgentCore Policy** | Cedar policy enforcement on tool calls via AgentCore Gateway | Gateway-only — doesn't cover inter-agent messages, non-Gateway actions, or agents not on AWS; deterministic rules only, no behavioral contract evaluation or drift detection; AWS-only, conflict of interest |
| **Amazon Bedrock Agent Registry** | Catalog/discovery of agent definitions, MCP servers, skills | Design-time catalog — not a runtime registry; no admission control for running instances; no lineage tracking for spawned agents; no lifecycle states for live agents |

### The AgentCore Policy Gap — Why It Matters

Amazon's Policy component is the most direct precursor to runtime governance in the market. It deserves a precise critique rather than a dismissal.

**What it gets right:** Cedar policies evaluate before a tool call executes — this is genuine pre-execution enforcement, not post-hoc logging. For tool calls that go through AgentCore Gateway, it works.

**Where it falls short:**

- **Coverage:** Only tool calls routed through AgentCore Gateway are covered. Direct API calls, inter-agent messages over NATS or ZMQ, and tool invocations that bypass Gateway are invisible to Policy. Civitas enforces at the transport layer — every message, regardless of how it's routed.
- **Depth:** Cedar policies are deterministic boolean rules. They cannot evaluate whether an agent is staying on-task, whether its outputs conform to a behavioral contract, or whether its behavior is drifting over time. That requires LLM-as-a-Judge — which AgentCore's Evaluations component provides, but only post-hoc, not in-flight.
- **Lineage:** AgentCore has no concept of a dynamically spawned sub-agent inheriting a constrained policy envelope from its parent. A spawned agent is ungoverned by Policy unless explicitly pre-configured.
- **Lock-in:** AWS-only. Agents running Claude via direct API, GPT-4, Gemini, or any local model outside Bedrock are not covered.
- **Conflict of interest:** AWS governs the same models it sells. Presidium governs none of the models it monitors.

The core gap: governance must be **in the execution path, across all agent actions, model-agnostically**. You cannot enforce a policy you are only observing — and you cannot govern agents you don't host.

---

## 2. Product Vision

### Vision Statement

Presidium is the runtime governance platform for autonomous AI systems — the layer that makes agents auditable, controllable, and explainable, not just observable.

It is built on Civitas, the open-source Python agent runtime, which sits beneath every agent framework in the execution path. Because Civitas is in the path, Presidium's governance is enforced before actions happen — not logged after.

### The One-Line Position

> **Presidium is the governance layer for the agentic AI era — the only platform that makes autonomous AI systems auditable, explainable, and controllable at runtime, not just on paper.**

### What Success Looks Like

A CISO at a Fortune 500 financial firm can open the Presidium Console and answer, in under 60 seconds:
1. What agents are running in my organization right now?
2. What did each agent do in the last 24 hours, and did any of them violate policy?
3. Are there any agents operating with credentials that shouldn't be active?
4. Show me the audit record for this specific agent decision — structured for our EU AI Act submission.

No other product in the market can answer all four questions. Presidium can.

---

## 3. Target Users

### Primary Buyers (Economic Decision Makers)

**P5 — CTO / VP Engineering**
The business sponsor. Approves the investment. Needs to answer the board question: *"What is our AI governance posture?"* Cares about organizational risk, regulatory exposure, and the ability to scale agent deployment without losing control.

**P4 — Compliance Officer / General Counsel**
The regulatory decision maker. Responsible for EU AI Act, SOC 2, HIPAA, SEC compliance. Needs structured audit exports, attestation capabilities, and documented policy enforcement — not just logs.

**P3 — CISO / Security Engineer**
The security decision maker. Concerned about agent credentials, lateral movement, blast radius. Needs agent identity management, independent of human IAM. Needs to be able to revoke an agent's access without revoking the delegating human's access.

### Primary Users (Day-to-Day)

**P1 — AI/ML Engineer**
Builds agents. Needs the runtime to be reliable and correctable. Adopts Civitas as the OSS runtime — gets governance primitives for free. Upgrades to Presidium when the team needs fleet management and behavioral contracts.

**P2 — Platform / MLOps Engineer**
Operates agent systems in production. Needs deployment primitives, monitoring, alerting, and the ability to pause or roll back misbehaving agents. Primary user of the Presidium Console day-to-day.

---

## 4. Product Scope

### What This Product Is

Presidium is a two-layer product:

**Layer A — Civitas Runtime (Open Source, Apache 2.0)**
The execution substrate. Distributed via PyPI (`pip install python-civitas`). Provides the governance primitives that make the commercial layer possible:
- Agent Registry (local, single-fleet)
- HITL checkpoint primitive
- Policy hook interfaces in the transport layer
- EvalLoop + CorrectionSignal
- Automatic OTEL telemetry

**Layer B — Presidium Console (Commercial)**
The enterprise control plane. SaaS or self-hosted. Consumes the telemetry and governance events emitted by Civitas-powered agents and provides:
- Fleet-level agent registry with lifecycle management
- Behavioral contracts + LLM-as-a-Judge continuous evaluation
- Immutable audit ledger (compliance-structured)
- Advanced policy engine with UI authoring and approval workflows
- Agent identity vault (scoped credentials, rotation, revocation)
- Compliance exports (EU AI Act, SOC 2, HIPAA, SEC)
- Blast radius dashboard with real-time circuit breakers
- HITL approval workflows (Slack, email, console)

### What This Product Is NOT

- Not an agent framework (Civitas wraps frameworks; it does not replace them)
- Not a model provider (governance is model-agnostic)
- Not a cloud service (deployable anywhere Python runs; no AWS/GCP/Azure dependency)
- Not a post-hoc audit tool (governance is enforced at runtime, before actions fire)

---

## 5. Core Features

### F1 — Agent Registry

**Problem it solves:** Enterprises cannot answer "what agents are running right now?"

**Description:**
A canonical, persistent record of every agent in the organization. The registry is the admission controller for the Civitas runtime — unregistered agents do not start.

**Key behaviors:**
- Every agent receives an immutable unique ID at registration time
- Registry entries include: owner, capabilities, trust tier, risk classification, environment, parent agent ID (for spawned agents)
- Dynamically spawned agents auto-register with their parent's ID; privilege cannot escalate through spawning
- Lifecycle states: `registered → active → flagged → deprecated → decommissioned`
- Owner notifications at lifecycle transitions
- Registry is the authoritative source for all downstream governance layers

**OSS scope:** Local registry, single-fleet, no UI
**Commercial scope:** Fleet-level registry, multi-environment, Presidium Console UI, search, filtering, bulk lifecycle management

---

### F2 — Agent Policy Engine

**Problem it solves:** Agents act beyond their intended mandate. Policies exist on paper but are not enforced.

**Description:**
Declarative, runtime-enforced policies on what each agent is permitted to do. Policy evaluation happens inside Civitas's transport layer — before the action executes.

**Key behaviors:**
- Policies attach to agent identities, not users — an agent's policy travels with it regardless of which human delegated it
- Policy dimensions: action type (send_email, execute_code, call_api), target (internal, external, specific domains), rate (N calls per window), environment (staging, production), monetary ceiling
- Policy violation outcomes: block, alert, require_approval, log_only
- Policies are versioned; each version is immutable after publication
- Policy changes require an approval workflow (configurable)
- Evaluation is synchronous and sub-millisecond (no impact on agent latency for allow decisions)

**OSS scope:** Policy hook interfaces; basic allow/block by action type via YAML config
**Commercial scope:** Full policy engine, UI authoring, versioning, approval workflows, cross-fleet policy inheritance

---

### F3 — Agent Identity & Credentialing

**Problem it solves:** Agents inherit human credentials, creating the "lethal trifecta" of access + exposure + authority.

**Description:**
Each agent gets its own scoped, rotatable, short-lived credentials — managed by Civitas's credential vault, independent of the human IAM system.

**Key behaviors:**
- Agent credentials are scoped to the specific actions and targets the agent's policy permits
- Credentials are short-lived (configurable TTL) and rotate automatically
- Downstream systems receive agent identity tokens, not user tokens — enabling "which agent did this?" attribution
- Credential revocation is independent of the delegating human's credentials
- Vault stores no plaintext secrets; all credentials are encrypted at rest and in transit
- Prompt injection attack surface reduced: an agent operating with agent-scoped credentials cannot exceed its policy envelope even if instructed to

**OSS scope:** Not included in OSS tier (security-critical commercial feature)
**Commercial scope:** Full credential vault, rotation, revocation, downstream system integration, audit log of all credential issuances

---

### F4 — Human-in-the-Loop Checkpoints

**Problem it solves:** High-stakes or irreversible agent actions execute without any human decision point.

**Description:**
A `checkpoint` primitive in Civitas that pauses agent execution at defined decision points and requests human approval before proceeding.

**Key behaviors:**
- Agent declares checkpoint conditions in its constitution or YAML config (e.g., `spend_exceeds: $500`, `action_type: send_external_email`, `file_write: /sensitive/*`)
- When a checkpoint condition is met, the agent pauses and emits an approval request
- Approval requests surface in: Presidium Console, Slack (via Presidium integration), email
- Approval request includes full context: what the agent intends to do, why (agent reasoning), the policy envelope, prior actions in this session
- Approvals are time-boxed (configurable); timeout behavior is configurable (default: deny and alert)
- Every approval or denial becomes a permanent, signed entry in the audit ledger
- Denied actions produce a `CorrectionSignal` that the agent receives with the denial reason

**OSS scope:** `checkpoint` primitive with basic console approval (blocking, CLI)
**Commercial scope:** Presidium Console approval UI, Slack integration, email integration, mobile approval, delegation workflows, time-box management

---

### F5 — Behavioral Contracts

**Problem it solves:** Agents drift from their intended behavior over time. There is no mechanism to continuously verify that an agent is acting within its designed purpose.

**Description:**
A versioned `CONSTITUTION` file attached to each agent defining its values, permitted behaviors, forbidden behaviors, and escalation triggers. Presidium's LLM-as-a-Judge evaluates agent outputs against the contract continuously.

**Key behaviors:**
- Constitution is a structured YAML/Markdown document committed alongside agent code
- Dimensions: purpose statement, permitted action categories, forbidden action categories, tone/style constraints, escalation triggers (score thresholds)
- Presidium's judge model evaluates each agent output against the constitution in near-real-time
- Evaluation scores feed back into Civitas via the EvalLoop → CorrectionSignal path
- Score trends are tracked over time — behavioral drift is visible as a trend, not just a point event
- Contracts are versioned; behavioral changes are tracked against contract versions for audit purposes

**OSS scope:** Constitution file format spec + EvalLoop integration hooks
**Commercial scope:** Judge model integration, scoring dashboard, drift alerts, contract versioning, comparison reports

---

### F6 — Immutable Audit Ledger

**Problem it solves:** Agent action logs do not capture the decision context needed for regulatory compliance.

**Description:**
Every agent action produces a signed, timestamped record anchored to the agent's registry ID. Records are immutable after creation and structured for regulatory export.

**Key behaviors:**
- Every message send/receive, tool invocation, LLM call, checkpoint event, and CorrectionSignal produces a ledger entry
- Each entry is signed with the agent's identity and a ledger sequence number (tamper-evident)
- Entries include: agent ID, action type, target, input hash, output hash, policy state at time of action, human approval ID (if applicable)
- Ledger is append-only; no modification or deletion
- Export formats: EU AI Act Article 13, SEC Rule 17a-4, SOC 2 Type II, HIPAA audit trail, DPDPA
- Retention policies configurable per environment; immutability guarantees maintained regardless

**OSS scope:** Not included in OSS tier (compliance-critical commercial feature)
**Commercial scope:** Full ledger, signing, tamper detection, compliance exports, retention management, eDiscovery search

---

### F7 — Blast Radius Controller

**Problem it solves:** A misbehaving agent can consume unlimited resources, spend unlimited budget, or perform unlimited external actions before anyone notices.

**Description:**
Resource quotas and circuit breakers per agent. Anomalous behavior triggers automatic suspension and escalation.

**Key behaviors:**
- Per-agent quotas: LLM calls per hour, token spend per day, external API calls per window, monetary ceiling
- Anomaly detection: statistical deviation from baseline triggers alert before limit is hit
- Circuit breaker: agent suspended automatically on quota breach or anomaly threshold; supervisor notified
- Blast radius visualization: Presidium Console shows each agent's current resource consumption against quotas in real time
- Suspension is reversible: operator can resume agent with or without quota adjustment
- Quota adjustments require policy approval workflow (configurable)

**OSS scope:** Basic per-agent quota config via YAML; suspension triggers EvalAgent halt signal
**Commercial scope:** Presidium Console visualization, anomaly detection, automated alerts, approval workflows for quota changes

---

## 6. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                  Presidium Console                   │
│  Registry UI · Policy Authoring · Audit Ledger · Compliance  │
│  Behavioral Contract Dashboard · Blast Radius · HITL UI      │
├───────────────────────────────┬──────────────────────────────┤
│   Behavioral Contracts        │   Immutable Audit Ledger     │
│   + LLM-as-a-Judge            │   + Blast Radius Controller  │
├───────────────────────────────┼──────────────────────────────┤
│   HITL Checkpoints            │   Agent Identity             │
│   (Slack · Email · Console)   │   & Credential Vault         │
├───────────────────────────────┼──────────────────────────────┤
│   Policy Engine               │   (Enforcement in transport) │
├───────────────────────────────┴──────────────────────────────┤
│                       Agent Registry                          │
│        Unique IDs · Lineage · Lifecycle · Trust Tiers        │
├──────────────────────────────────────────────────────────────┤
│                       Civitas Runtime                          │
│     Transport · MessageBus · Supervision · EvalLoop          │
│     Heartbeat · State Persistence · OTEL Telemetry           │
└──────────────────────────────────────────────────────────────┘
          ↑ LangGraph / CrewAI / OpenAI SDK / Strands / custom
```

**Data flow:**
1. Agent action → Civitas transport layer → Policy Engine (enforce or block)
2. Action executes → OTEL span emitted → Presidium receives enriched telemetry
3. Presidium's judge model evaluates output against Behavioral Contract → score
4. Score below threshold → EvalAgent emits CorrectionSignal → agent receives and adjusts
5. Every event → Audit Ledger entry (signed, timestamped)
6. Quota exceeded → Blast Radius Controller suspends agent → Console alert fires

---

## 7. Integration Paths

Governance value should be accessible to teams regardless of whether they adopt Civitas as their runtime. Two paths exist, with different coverage and enforcement guarantees.

---

### Path A — Civitas-Native (Full Governance)

The recommended path. Civitas sits beneath the agent framework in the execution path. Governance is universal, automatic, and enforced before actions fire.

**How it works:**
- Agent code runs inside `AgentProcess` (directly or via framework adapters for LangGraph, CrewAI, OpenAI SDK)
- Every message, tool call, LLM invocation, and supervision event passes through Civitas's transport layer
- Policy enforcement, HITL checkpoints, and blast radius controls happen at the transport layer — no developer instrumentation required
- Registry, identity, and audit ledger receive structured events automatically via OTEL

**Coverage:** Complete. All governance layers enforced.

**Entry point:** `pip install python-civitas[fiddler]`

---

### Path B — Framework Plugin (Partial Governance)

For teams already in production with LangGraph, CrewAI, or OpenAI Agents SDK who are not ready to adopt Civitas as the runtime. Presidium provides per-framework instrumentation plugins that deliver observability and post-hoc governance — but not runtime enforcement.

**How it works:**
- Presidium plugin installs as a callback/middleware in the existing framework
- LLM inputs/outputs, tool calls, and agent events are captured and forwarded to Presidium
- Behavioral contracts, audit ledger, and blast radius alerting work based on observed telemetry
- Policy enforcement and HITL checkpoints are NOT available — no enforcement point exists in the execution path without a runtime

**Coverage:** Layers 1 (Registry — manual registration), 5 (Behavioral Contracts + Audit Ledger), 7 (Blast Radius — alerting only, no circuit breaker). Layers 2, 3, 4 require Civitas.

**Entry point:** `pip install fiddler-langchain` / `fiddler-crewai` / `fiddler-openai`

**Migration path:** Path B customers naturally graduate to Path A as their agent fleet grows and enforcement requirements tighten. The Presidium console, behavioral contracts, and audit ledger work identically on both paths — no data loss or reconfiguration on upgrade.

---

### Path Comparison

| Capability | Path A (Civitas-native) | Path B (Framework plugin) |
|---|---|---|
| Agent Registry | Full — admission controller, no unregistered agent starts | Partial — manual registration on startup |
| Policy enforcement | Runtime — before action fires | None |
| Agent Identity & Credentialing | Full | None |
| HITL Checkpoints | Full — agent pauses, approval required | None |
| Behavioral Contracts | Full — eval loop + correction signal | Observational — scoring only, no in-flight correction |
| Audit Ledger | Full — every event, signed | Partial — LLM calls and tool invocations only |
| Blast Radius Controller | Full — circuit breaker + suspension | Alert only — no automatic suspension |
| Dynamic agent spawning governance | Full (pending `Runtime.attach()`) | None |

---

### Runtime Gap: Dynamic Agent Attachment

**Current state of Civitas (as of M2.8):** The runtime has no public API for dynamically attaching a new `AgentProcess` to a running instance. The startup sequence in `Runtime.start()` is a one-time initialization — it walks the supervision tree, injects components, registers agents, and sets up transport subscriptions. There is no `runtime.attach()` or `supervisor.add_child()` method.

**Why this matters for governance:** Agentic systems routinely spawn sub-agents at runtime (a research orchestrator spinning up specialized tool agents, a customer support agent spawning a billing sub-agent). Without dynamic attachment:
- Spawned agents are unregistered — they bypass the admission controller
- They have no supervision coverage — a crash is undetected
- They generate no governed telemetry — invisible to the audit ledger
- They cannot have scoped credentials — they inherit the parent's credential envelope

This is precisely the privilege escalation path the governance stack is designed to prevent.

**Required Civitas work — `Runtime.attach()`:**
A new method on `Runtime` that performs the full wiring sequence for a dynamically created agent:
1. `cs.inject(agent)` — wire transport, tracer, model provider, state store
2. `registry.register(agent.name, parent_id=spawning_agent.id)` — admission control with lineage
3. `await bus.setup_agent(agent)` — transport subscription
4. `supervisor.add_child(agent)` — bring under supervision coverage
5. `await agent.start()` — start the process

This also requires `Supervisor.add_child()` to exist, which it currently does not.

**Ownership: Civitas core, not governance.** `self.spawn()` and `Runtime.attach()` are runtime mechanics — how a new process comes into existence and gets wired into the running system. This is the same class of primitive as Erlang/OTP's `spawn/1`. The governance layer does not own this capability; it hooks into it via the `on_spawn_requested` policy interface:

```
self.spawn() called
    → on_spawn_requested hook fires
    → Policy Engine checks parent's spawn capability
    → allowed: Runtime.attach() proceeds, lineage recorded in Registry
    → denied:  PolicyViolation raised, parent receives structured error, audit ledger entry written
```

The primitive ships as **Civitas core M4.1b**. The governance hooks (policy check, lineage recording, audit entry) are the Presidium governance layer's responsibility and activate automatically when the Presidium plugin is present.

**Until this is built:** Dynamically spawned agents are a governance blind spot on Path A. Path B has the same gap. Customers with spawning patterns must pre-declare all possible agent types in the topology — a significant constraint for dynamic multi-agent systems.

**Priority:** High. This is a prerequisite for the governance claim that "no agent runs without a registry entry."

---

## 8. Open Source Strategy

### Why open source the runtime

Civitas is the adoption engine. Developers adopt the runtime first. Governance primitives embedded in the runtime create the data pipeline and integration surface that makes the commercial layer valuable. An enterprise cannot adopt Presidium Governance without Civitas — and Civitas is free.

The open-source/commercial split:
- **OSS (Civitas):** Runtime, supervision, basic registry, HITL primitive, EvalLoop, OTEL telemetry, policy hook interfaces, constitution format spec
- **Commercial (Presidium):** Fleet management, advanced policy engine, credential vault, compliance audit ledger, LLM-as-a-Judge at scale, enterprise console

This mirrors proven open-core models (HashiCorp, Elastic, Temporal) where the OSS layer is genuinely useful and the commercial layer adds enterprise-critical capabilities the OSS layer deliberately does not include.

### Community positioning

Civitas competes and wins on "reliable multi-agent systems" — the use case where supervision trees, message passing, and fault tolerance matter. This is the audience that will eventually face governance requirements. The OSS-to-commercial conversion is a natural upgrade, not a trap door.

---

## 8. Success Metrics

### Adoption (Civitas OSS)
- PyPI downloads per month
- GitHub stars and forks
- Community agents published (AGENTS.md ecosystem)
- Framework adapter usage (LangGraph, CrewAI, OpenAI SDK wraps)

### Activation (Presidium Integration)
- `python-civitas[fiddler]` installs as % of total Civitas installs
- Time from Civitas install to first Presidium telemetry event
- Organizations with active Presidium + Civitas integration

### Governance Value (Commercial)
- Agents registered in Presidium Registry per customer
- Policy violations caught and blocked per month
- HITL checkpoints triggered and approved
- Compliance exports generated
- Mean time from agent anomaly to suspension (blast radius control)

### Business
- Annual Recurring Revenue from Presidium tier
- Conversion rate: Civitas OSS users → Presidium paid customers
- Net Revenue Retention (governance customers expand as agent fleet grows)
- Enterprises closed in regulated industries (financial services, healthcare, government)

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cloud providers build this natively | High (medium-term) | High | Move fast; establish OSS community; win on neutrality (they govern their own models) |
| Civitas adoption slower than expected | Medium | High | Strong AGENTS.md, examples, and coding agent discovery; progressive disclosure of complexity |
| Governance overhead degrades agent performance | Medium | Medium | Policy evaluation is sub-millisecond for allow decisions; async audit writes; benchmark publicly |
| LLM-as-a-Judge cost at scale | Medium | Medium | Configurable evaluation frequency; sampling strategies for high-volume agents; cost dashboard |
| Regulatory requirements change faster than product | Low | High | Constitution format is versioned; compliance exports are configurable; track EU AI Act evolution closely |
| Enterprise security review rejects OSS runtime in critical path | Low | High | Apache 2.0 license; SOC 2 Type II for Presidium-hosted components; self-hosted option |
| Dynamically spawned agents bypass governance | High (current) | High | `Runtime.attach()` is a required Civitas feature before governance can be claimed complete; block GA on this |

---

## 10. Open Questions

- [ ] **Pricing model:** Per-agent registered? Per-governance event? Per-seat (console users)? Combination?
- [ ] **Self-hosted vs. SaaS:** Which tier of customer prefers which? What is the deployment story for air-gapped environments (financial services)?
- [ ] **Agent Registry identity:** Should agent IDs be cryptographically anchored (DID-style) or registry-internal UUIDs?
- [ ] **Multi-tenant isolation:** How is the governance console scoped for enterprises with multiple internal teams? Business unit isolation? Project isolation?
- [ ] **Judge model selection:** Is Presidium's judge model configurable per customer, or standardized? What are the compliance implications of using a cloud-hosted judge model to evaluate sensitive agent outputs?
- [ ] **A2A protocol integration:** As the Agent-to-Agent (A2A) protocol matures, governance must extend to cross-organization agent interactions. What does that look like?
- [ ] **Incident response:** When the Blast Radius Controller suspends an agent mid-workflow, what is the recovery story? Does the audit ledger capture enough context to reconstruct state?
- [ ] **`Runtime.attach()` scope:** Should dynamic attachment be gated behind a governance policy (i.e., a spawning agent must have `spawn` in its permitted capabilities before `attach()` succeeds)? If yes, this becomes the enforcement point for preventing privilege escalation through spawning.
- [ ] **Path B graduation triggers:** What signals in Presidium telemetry should prompt a Path B customer to migrate to Path A? (e.g., first dynamic spawning pattern detected, first policy violation that couldn't be blocked, first compliance export gap)
