# RFC-001: Presidium Scope and Boundaries

**Status:** Draft (revised 2026-05-05)
**Author:** Jeryn Mathew
**Created:** 2026-04-30
**Revised:** 2026-05-05 — Added AAA architecture, clarified capability/grant distinction, renamed `presidium-eval` → `presidium-audit`, formalized integration points.

---

## Summary

This RFC defines what Presidium is, what it isn't, and the exact boundaries between Presidium, Civitas, and external platforms — including a holistic view of Authentication, Authorization, and Access Control (AAA) across both layers.

## Motivation

Presidium could become many things: a framework, a platform, an observability tool, a compliance engine. Without explicit scope boundaries, features end up in the wrong layer, names conflict, and customers face contradictions. This RFC is the governing document. All package proposals must align with it.

---

## The One-Line Separation

> **Civitas**: Run agents reliably.
> **Presidium**: Run agents accountably.

These are additive. A customer never has to choose between a Civitas feature and a Presidium feature for the same job. Civitas is complete and useful without Presidium. Presidium is meaningless without Civitas.

---

## Scope: What Presidium IS

Presidium is a **governance layer for AI agent systems**, built on Civitas. It provides five capabilities:

1. **Agent Registry** — persistent agent identity (name, version, owner, lifecycle state, trust score) integrated with enterprise IdPs
2. **Policy Engine** — declarative policies enforced at runtime (ALLOW, DENY, REQUIRE_APPROVAL); Cedar primary, OPA supported
3. **Identity & Credentials** — agent identity grants (authorization), credential vault (OAuth tokens, API keys scoped per agent + user), token exchange for user-delegated access
4. **Gateways** — governed LLM access (`GovernedModelProvider`) and governed tool access (`GovernedToolProvider`); wrap Civitas plugins, enforce grants and policy
5. **Audit & Compliance** — governance metrics, policy compliance reporting, trust score tracking, external platform export (Fiddler, Arize, Langfuse)

### Design Principles

- Governance is **architectural**, not bolted on — policy constraints integrate into Civitas supervision, not a sidecar
- **Integration over implementation** — integrate with enterprise IdPs (Entra, Okta, Google IAM, AWS IAM); do not build a new IdP
- **Python-first** — no multi-language until Python is excellent
- **Developer-centric** — simple things simple, complex things possible
- **Vendor-neutral** — no cloud lock-in; OTEL for telemetry
- **Open source core** — Apache 2.0, free forever for core governance primitives

---

## Out of Scope: What Presidium is NOT

| NOT This | That's This | Why |
|----------|-------------|-----|
| Agent framework | LangGraph, CrewAI, OpenAI Agents SDK | Presidium governs agents; doesn't define how they reason |
| Agent runtime | Civitas | Presidium depends on Civitas; doesn't replace it |
| Identity Provider (IdP) | Entra, Okta, Auth0, Keycloak, Google IAM, AWS IAM | Presidium integrates with IdPs; does not issue identity tokens |
| Observability platform | Fiddler, Arize, Langfuse | Presidium generates governance telemetry; they dashboard it |
| Content safety / guardrails | Fiddler Guardrails, NeMo Guardrails | Presidium governs structural access; not content quality |
| LLM provider | Anthropic, OpenAI, Google | Presidium routes to providers; does not serve models |
| Web dashboard | Future project (cloud tier) | Presidium is a library/runtime; not a UI |
| Model routing / fallback | Civitas `CompositeModelProvider` (thin utility) | Model routing without governance is infrastructure, not governance |

---

## Boundary: Civitas vs. Presidium

### What Civitas Provides (the runtime layer)

- Supervision trees, restart strategies, fault tolerance, escalation
- Message passing, mailboxes, backpressure, bus routing
- Transport abstraction (InProcess, ZMQ, NATS) with mTLS
- **Operational routing registry** — where agents are, what capability tags they advertise (routing, not authorization)
- **Capability routing tags** — operational tags on `AgentProcess` that drive `send_capable()` routing; these are about what an agent *can handle technically*, not what it is *authorized to do*
- State persistence (InMemory, SQLite, Postgres)
- OTEL tracing, audit event emission pipeline (`AuditSink`)
- Plugin interfaces: `ModelProvider`, `ToolProvider`, `StateStore`, `ExportBackend`
- Concrete plugins: Anthropic, OpenAI, Gemini, Mistral, LiteLLM, NATS, ZMQ, Postgres
- MCP client integration (connectivity mechanics)
- HTTP Gateway (infrastructure edge)
- EvalLoop (agent self-correction signals — separate from governance audit)
- GenServer (OTP-style stateful service process)
- Fabrica (tool namespace, agent-as-tool) — planned v0.5
- Skills Gateway (named composable workflows) — planned v0.5
- Prompt Library (PromptStore GenServer) — planned v0.5
- **Extension hooks** for Presidium: `RegistryListener`, plugin protocols, `AuditSink`

Civitas does **not** provide:
- Persistent agent identity (no owner, no version, no trust score)
- Authorization policy enforcement
- Per-agent resource governance (rate limits, budgets)
- Credential vault or token exchange
- HITL approval routing or approver authentication
- Compliance reporting

### What Presidium Provides (the governance layer)

- **Agent identity** — persistent: name, version, owner, registered_at, lifecycle state. Survives restarts. Linked to IdP service principals.
- **Agent grants** — authorization entitlements: what an agent is *permitted to access* (tool namespaces, LLM tiers, data scopes). Distinct from Civitas capability routing tags.
- **Trust scores** — numeric, decays over time, updated by policy compliance signals
- **Policy engine** — Cedar (primary) and OPA (plugin): evaluates `(agent, action, resource, context)` → ALLOW / DENY / REQUIRE_APPROVAL
- **Identity & credentials** — credential vault scoped per `(agent_id, user_id)` tuple; token exchange (OBO, XAA/ID-JAG, client credentials); enterprise IdP integrations (Entra, Okta, Google, AWS IAM)
- **LLM Gateway** (`GovernedModelProvider`) — wraps any Civitas `ModelProvider`; enforces per-agent rate limits, cost tracking, budget enforcement, grant-based provider routing
- **MCP Gateway** (`GovernedToolProvider`) — wraps Civitas MCP client; enforces tool ACLs per agent grants, tool poisoning detection (snapshot hashes), credential redaction, audit logging
- **HITL approval** — durable approval requests, signed payloads (LITL protection), approver authentication via org IdP
- **Audit & compliance** (`presidium-audit`) — governance metrics (policy compliance rate, denial counts, trust drift, budget utilization), external platform export, compliance report generation

Presidium does **not** provide:
- The runtime itself (depends on Civitas)
- Basic model calling (wraps Civitas ModelProvider)
- Basic tool calling (wraps Civitas MCP)
- Dashboards (generates telemetry; external platforms render it)
- Content quality scoring (guardrails, not governance)

---

## Capability Tags vs. Grants: A Critical Distinction

**These are different concepts. Do not conflate them.**

| Concept | Layer | Meaning | Used for |
|---------|-------|---------|----------|
| **Capability tag** | Civitas | What an agent *can handle technically* | Routing: `send_capable("text.summarize")` dispatches to any capable agent |
| **Grant** | Presidium | What an agent is *authorized to access* | Authorization: `tool:database:read` determines if the agent can call the DB tool |

A capability tag is operational and routing-scoped. An agent may declare `capabilities = ["text.summarize"]` and never be authorized (granted) to use any tools. A grant is a governance entitlement — it is checked by the policy engine and the gateways before any resource access occurs.

In code: Civitas uses `AgentProcess.capabilities` (list of routing strings). Presidium uses `AgentRecord.grants` (list of authorization entitlements, e.g. `"tool:database:read"`, `"llm:claude-sonnet"`, `"data:customer_pii:read"`).

---

## AAA Architecture: Holistic View

Authentication, Authorization, and Access Control span both layers. Neither layer owns all of AAA. The boundary is clean:

### Authentication

**Who authenticates what:**

| Subject | Mechanism | Owner |
|---------|-----------|-------|
| Agent process → authorization server | OAuth 2.1 client credentials (client ID + secret or certificate) | Presidium credential vault issues the client credentials |
| Agent → MCP server | OAuth 2.1 Bearer token (JWT) with PKCE + Resource Indicators | Presidium MCP Gateway handles token acquisition |
| User → agent-facing application | OIDC/OAuth 2.0 via org IdP (Entra, Okta, Google) | Platform or application layer — Presidium integrates, does not implement |
| Agent acting on behalf of user | OBO / XAA / ID-JAG token exchange | Presidium credential vault + token exchange service |
| Agent → agent (A2A) | JWT Bearer token (A2A protocol / OIDC-A) | Presidium issues agent-to-agent tokens; Civitas transports them |
| Human approver (HITL) | OIDC via org IdP | Presidium approval service authenticates approver before recording decision |

**Civitas's role in authentication**: Transport-level (mTLS between nodes, already implemented in M4.2b). Civitas does not validate application-level tokens — that is Presidium's job.

### Authorization

**Who makes authorization decisions:**

| Decision | Who Makes It | How |
|----------|-------------|-----|
| Can agent A call tool T? | Presidium policy engine | Cedar policy: agent grants ∩ tool ACL |
| Can agent A call LLM with model M? | Presidium policy engine | Agent grants include `llm:<model>` |
| Can agent A spend more budget today? | Presidium budget tracker | Per-agent cost tracking against configured limits |
| Can agent A send a message to agent B? | Civitas routing registry | B is registered and reachable (operational, not governance) |
| Can user U approve action X? | Presidium HITL service | Approver's IdP role + Conditional Access policy |

### Access Control

**The MCP access control stack (bottom to top):**

```
MCP Server (resource)
  ↑ OAuth 2.1 Bearer token with scopes
Presidium MCP Gateway
  ↑ Agent grants + policy engine decision
Civitas AgentProcess (client)
  ↑ Credential context injected at startup by Presidium
```

**The LLM access control stack:**
```
LLM Provider API (Anthropic, OpenAI, etc.)
  ↑ API key or OAuth token from Presidium credential vault
Presidium GovernedModelProvider
  ↑ Rate limit check + budget check + grant check
Civitas ModelProvider protocol
  ↑ Agent calls provider.chat(...)
```

### Credential Flow

The canonical flow for any resource access:

```
1. Presidium issues agent credentials at startup
   (client ID/secret or short-lived JWT for the agent identity)

2. Agent needs to access a tool or LLM:
   Agent → Presidium credential vault (authenticated via agent credentials)
   Presidium validates grants, applies policy → returns scoped token

3. Agent presents scoped token to MCP server or LLM API

4. If user-delegated:
   User authenticates to org IdP → user token
   Agent exchanges user token via OBO/XAA → (agent_id, user_id) scoped token
   Resulting token permissions = intersection(agent grants, user delegated scope)
```

This maps to the OAuth 2.1 authorization server / resource server split: **Presidium is the authorization server; Civitas agents are clients; MCP servers and LLM APIs are resource servers.**

### HITL Authorization Pattern

```
1. Agent calls await self.request_approval(action=..., payload=...)
   (Civitas provides the durable suspension mechanism)

2. Presidium approval service receives the request:
   a. Signs the structured action payload (LITL protection — prevents UI manipulation)
   b. Routes notification to approver via configured channel (Slack, Teams, email)
   c. Notification contains a signed one-time token binding: action, decision, approver identity, expiry

3. Approver authenticates to org IdP (Entra SSO, Okta, etc.) via the notification link

4. Approver's authenticated identity is verified against approval policy
   (e.g., only users with role "senior-reviewer" can approve production writes)

5. Presidium records the decision with: action payload hash, approver identity, timestamp, channel
   and sends a resume signal to the suspended Civitas agent

6. Agent resumes with approval decision in its message context
```

---

## The Eight Integration Points

Where Civitas ends and Presidium begins — these are the only surfaces that cross the boundary:

| # | Hook | Civitas Provides | Presidium Consumes |
|---|------|-----------------|-------------------|
| 1 | `RegistryListener` | Async callback on every agent register/deregister, carrying name + capability tags | Populates `AgentRecord` in persistent Agent Registry |
| 2 | `ModelProvider` protocol | Interface: `chat(messages, agent_name, **kwargs) → ModelResponse` | `GovernedModelProvider` wraps any Civitas provider with rate limits, cost tracking, grant checks |
| 3 | `ToolProvider` protocol | Interface for tool calls via MCP client | `GovernedToolProvider` wraps with tool ACLs, poisoning detection, credential redaction |
| 4 | `AuditSink` | Pipeline: agent emits structured audit events | Presidium audit sink aggregates, enriches with governance context, exports to external platforms |
| 5 | `ExportBackend` | Interface for telemetry export | Presidium implements: `FiddlerExporter`, `ArizeExporter`, `LangfuseExporter` |
| 6 | `EvalLoop` hooks | Correction signal infrastructure for agent self-improvement | Presidium attaches governance metrics (compliance rate, denial count, trust delta) alongside self-correction signals |
| 7 | Credential context injection | Agent receives a `credentials` context at startup (opaque dict) | Presidium populates it: agent client credentials, initial token, vault endpoint, agent's grants |
| 8 | Durable suspension | `AgentProcess` can suspend execution awaiting an external signal | Presidium HITL service sends the resume signal after human approval |

---

## External Platform Boundary

Presidium generates governance signals. External platforms consume them.

| Signal | Presidium Generates | External Platform Consumes |
|--------|--------------------|-----------------------------|
| OTEL spans (governance-enriched, with agent identity + policy decision) | ✅ | Fiddler, Datadog, Jaeger |
| Governance metrics (compliance rate, trust drift, denial counts, budget utilization) | ✅ | Fiddler, Arize, Langfuse, Prometheus |
| Policy decision logs | ✅ | SIEM, audit systems (Splunk, Sentinel) |
| Trust score history | ✅ | Prometheus, Grafana |
| Approval audit trail (approver identity, decision, timestamp) | ✅ | GRC platforms, compliance audit |

Presidium does **not**:
- Build dashboards (external platform's job)
- Score content quality or detect hallucinations (guardrails are not governance)
- Issue compliance certificates (human audit process)
- Implement an IdP (integrates with IdPs; does not replace them)

---

## Decision

Accept this RFC as the governing scope document for Presidium. All package proposals must demonstrate alignment. Features that cross the boundary must be proposed as separate RFCs with explicit justification.

**Changes made in the 2026-05-05 revision:**
- Renamed `capabilities` → `grants` in `AgentRecord` throughout Presidium (avoids collision with Civitas capability routing tags)
- Renamed `presidium-eval` → `presidium-audit` (clearer: governance audit is distinct from agent self-correction eval, which is Civitas's EvalLoop)
- Removed "LLM Gateway" from Civitas — model routing without governance is a thin utility, not a gateway; the full governed gateway belongs in Presidium
- Added comprehensive AAA architecture section
- Formalized eight integration points (previously informal)
- Added Identity & Credentials as an explicit Presidium concern (credential vault, token exchange, IdP integration surface)

## Open Questions

- Should Presidium include a minimal TUI for local development? (Not a web UI — a `presidium status` terminal view of which agents are running, their trust scores, recent policy decisions.)
- At what point does Presidium need its own CLI vs. extending `civitas` CLI? Proposal: `presidium` CLI for governance commands (`presidium policy validate`, `presidium registry list`, `presidium audit export`); the `civitas` CLI remains for runtime operations.
- Should `presidium-sdk` re-export Civitas APIs or keep them as separate imports? Leaning toward separate — customers should know they're using both layers.
- Cedar vs. OPA as primary policy engine: Cedar is faster and formally verifiable; OPA has broader ecosystem. Proposal: Cedar primary (best-in-class for authorization), OPA supported via plugin adapter.
