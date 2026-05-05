# AAA Patterns for AI Agent Systems

> Research archive: Authentication, Authorization, and Access Control patterns across the industry.
> Last updated: 2026-05-05

This document captures how leading agent platforms and governance tools handle AAA — synthesized from production deployments, specifications, and public documentation. It informs Presidium's design decisions and scope boundaries.

---

## The Four Dominant Patterns

After surveying all major platforms (Microsoft, Google, AWS, LangGraph, CrewAI, Temporal, Portkey, Kong), four patterns account for ~90% of what is actually deployed or productizing.

---

### Pattern 1: OAuth 2.1 Client Credentials + JWT Bearer (Autonomous M2M)

**The baseline pattern for any agent-to-service call without a user in the loop.**

The agent authenticates to an authorization server using the `client_credentials` grant — no user involved. It receives a short-lived JWT (typically 15–60 minutes) and presents it as a Bearer token on every tool or API call. The resource server validates signature, expiry, audience, and scopes. No secrets in code — agent authenticates with a client ID and either a client secret or a client certificate (certificate preferred for high-assurance environments).

**MCP-specific augmentation**: Add [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707) Resource Indicators so each token is bound to the specific MCP server endpoint. A token obtained for MCP Server A cannot be replayed against MCP Server B. Add PKCE (replacing client secret) when the agent runs in environments where secrets cannot be stored safely (containers, serverless).

**Who uses it**: Every platform as the baseline. LangGraph (via developer-supplied auth handler), Temporal workflow clients, Kong/Portkey gateway auth, MCP server access for autonomous agents.

---

### Pattern 2: Token Exchange / On-Behalf-Of (OBO) for User-Delegated Access

**The critical pattern for "agent acts on behalf of the user."**

When an agent needs to access user-owned resources (email, calendar, files, CRM records), `client_credentials` is wrong — the resource server needs to know *which user* authorized this. Three concrete implementations:

- **Microsoft OBO (RFC 8693 / Entra)**: Exchange a user's access token for a new token that carries both user identity (`sub` claim) and agent identity (`act` claim). Downstream resources see both. RBAC can be applied on either dimension.
- **Okta Cross-App Access (XAA) / IETF ID-JAG**: Enterprise IdP acts as a trusted broker. Agent requests access to App B for User X. Okta evaluates enterprise policy (role, device posture, conditional access). If approved, issues a signed identity assertion JWT to the agent. App B trusts Okta's vouching, issues a scoped token. Full audit trail. No per-user consent screen after initial setup — policy governs.
- **AWS AgentCore 3LO**: Agent presents a user consent URL once. User consents. Token stored in AgentCore's credential vault. On future calls, agent retrieves the vault token by proving its Workload Identity — no repeated consent.

**Emerging IETF standard**: [draft-oauth-ai-agents-on-behalf-of-user-02](https://datatracker.ietf.org/doc/html/draft-oauth-ai-agents-on-behalf-of-user-02) (August 2025) formalizes this with an `actor_token` parameter identifying the specific agent during token exchange, producing tokens with both `sub` (user) and `act` (agent) claims.

**Key security property**: The resulting token's permissions are the *intersection* of what the agent is granted and what the user has delegated. Neither party can unilaterally expand the scope.

---

### Pattern 3: Per-Agent Cryptographic Workload Identity

**The high-assurance pattern. Currently only Google and AWS AgentCore in production.**

Instead of a shared service account or API key identifying "this is Agent Type X," each *deployed agent instance* gets a unique cryptographic identity at runtime.

- **Google**: SPIFFE ID + auto-rotating X.509 certificate (24-hour lifetime). Access tokens are cryptographically bound to the certificate — a stolen token without the cert is useless. mTLS enforced for all tool access.
- **AWS AgentCore**: Workload Identity ARN, unique per runtime. Tokens bound to a `(workload_id, user_id)` tuple — an agent cannot steal credentials from another agent instance even of the same type.
- **Microsoft Entra Agent ID**: Each agent gets a distinct service principal — no credentials of its own, derives tokens from a blueprint's managed identity. Every agent identity requires a human *sponsor*; if the sponsor leaves, sponsorship auto-transfers to their manager. Full non-repudiation — every action is attributable to a specific agent principal, not just a service role.

**Operational cost**: Requires a managed identity infrastructure (SPIFFE/SPIRE, AWS IAM, Entra managed identity). Not viable for simple/development deployments; essential for regulated enterprise environments.

---

### Pattern 4: Policy-as-Code at the Authorization Layer

**Runtime authorization decisions, separate from identity.**

Instead of embedding authorization logic in agent code or relying solely on IdP-issued scope strings, a standalone policy engine evaluates access decisions at runtime.

| Engine | Language | Strengths | Notes |
|--------|----------|-----------|-------|
| **Cedar** (AWS) | Structured, typed | 42–60x faster than Rego. Formally verifiable (mathematical proof policies are correct). Readable for security reviewers. | Used in AgentCore, Permit.io Cedar integration |
| **OPA / Rego** | Rego DSL | General-purpose. Widely used in Kubernetes/infra. Large ecosystem. | Enterprise support uncertain post Apple acquisition of maintainers (Aug 2025) |
| **Zanzibar** (Google model; Authzed/SpiceDB) | Relationship tuples | Best for graph-shaped authorization ("Agent X can access resources owned by members of Group Y") | Internal Google; open implementations available |

**The agent-system pattern:**
1. Agent attempts a tool call.
2. Gateway/runtime intercepts and sends an authorization query to the policy engine: `{ agent: {...claims}, action: "invoke_tool", resource: "delete_record", context: { user: {...}, approval_state: ..., time: ... } }`.
3. Policy engine returns `allow`, `deny`, or `require_approval`.
4. Policy files are version-controlled, auditable, and changeable without deploying agent code.

**Who uses it**: Kong (tool ACLs at gateway), AWS AgentCore (Cedar), Permit.io, Google (Zanzibar internal). Microsoft uses Entra RBAC + Conditional Access as its policy layer.

---

## MCP + OAuth 2.1: The Specification

As of the March 2026 MCP specification, authorization is standardized around OAuth 2.1. The concrete architecture:

**Roles:**
- **MCP Server** = OAuth 2.1 Resource Server (accepts and validates access tokens)
- **MCP Client** (the agent) = OAuth 2.1 Client (obtains tokens and makes protected requests)
- **Authorization Server** = Your IdP (Entra, Keycloak, Auth0, Okta) — MCP does not provide one

**Discovery (mandatory per spec):**
MCP servers MUST implement [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728) (OAuth 2.0 Protected Resource Metadata). Clients discover the authorization server from the resource server's metadata endpoint.

**Token acquisition flow:**
1. Client hits MCP server, gets 401 with `WWW-Authenticate` header pointing to the authorization server.
2. Client fetches Protected Resource Metadata.
3. Client initiates OAuth 2.1 Authorization Code + PKCE (PKCE mandatory in all environments).
4. **Resource Indicators (RFC 8707) — mandatory in the 2026-03-15 spec.** The client specifies the MCP server as the intended recipient. Prevents token mis-redemption attacks.
5. Client presents token to MCP server. Server validates signature, expiry, audience, and scopes.

**Scope patterns:**
- Coarse: `mcp:tools`, `mcp:resources` — access to the whole category.
- Fine-grained: `mcp:tools:search`, `mcp:tools:delete` — per-tool scopes, configured at the authorization server.
- Gateway-level ACLs (Kong, Portkey, Presidium MCP Gateway) can enforce finer granularity without modifying the MCP server.

**Enterprise pattern (added Nov 2025):** Cross-App Access / ID-JAG incorporated as an Authorization Extension. Enterprise IdP mediates the agent-to-MCP-server connection. Centralized visibility and policy enforcement. Users consent once; subsequent accesses are policy-governed.

---

## HITL: Human Approval Auth Patterns

The core challenge: an agent pauses mid-execution and routes an approval request to a human. How do you authenticate the approver? How do you prevent dialog forgery (LITL attacks)?

### Pattern A: Durable Workflow Signal

Workflow suspends durably (no polling; state persisted). An external notification (Slack, email) is sent with a unique callback. The human's approval action sends a Signal (Temporal) or Resume (LangGraph `interrupt()`) to the workflow engine. The UI/Slack bot/email handler authenticates the human with the org's IdP (OAuth/OIDC) before accepting the signal. The human's authenticated identity is attached to the signal payload and stored durably as audit evidence.

**Temporal's implementation**: Approval request sent via email/Teams. Human clicks link, authenticates via org SSO, clicks Approve. This triggers a Temporal Signal. The Signal carries the approver's authenticated identity. The workflow resumes with full provenance.

### Pattern B: Signed One-Time Token in Notification

Agent generates a short-lived signed JWT containing: action ID, permitted decision, expiry, and binding to the specific approver's identity. Token is embedded in an approval link. Approval endpoint validates JWT (signature, expiry, binding) before recording the decision. Token is single-use (consumed on first redemption). Prevents replay attacks.

**LITL protection**: The structured approval payload (what the agent will actually execute) is generated and cryptographically signed *before* rendering anything to the human. The UI is rendered from that signed payload — not from LLM output. This prevents malicious content from manipulating the approval dialog.

### Pattern C: Interactive Slack/Teams Bot with OAuth

Slack sends interactive message blocks with Approve/Deny buttons. Button clicks generate Slack webhook callbacks authenticated with the bot's OAuth token. Slack workspace provides the human's authenticated identity via `user_id` in the payload. Rich formatting + threaded conversations for context.

**Microsoft Agent Framework HITL**: Approval requests sent to Teams/Outlook via Microsoft Graph. Approver authenticates via Entra SSO. Approval tied to Entra identity, logged in agent's audit trail. Conditional Access policies can restrict who is eligible to approve specific action types.

---

## Competitor AAA Summary

| Platform | Agent Identity | Authorization | HITL | IdP Integration |
|----------|---------------|---------------|------|-----------------|
| **Microsoft Entra Agent ID** | Service principal per agent, blueprint-derived | Entra RBAC + Conditional Access | Teams/Outlook via Graph, Entra SSO for approvers | Native (Entra is the IdP) |
| **Google Vertex AI** | SPIFFE/X.509 per instance, cert-bound tokens | IAM + Cedar | Not built-in | Workload Identity Federation (any IdP) |
| **AWS AgentCore** | Workload Identity ARN | Cedar policy engine | Not built-in | Cognito + any OAuth IdP via token exchange |
| **LangGraph Platform** | Developer-defined (pluggable) | Developer-defined (pluggable) | `interrupt()` suspend, developer handles routing | Developer-supplied OAuth/OIDC handler |
| **CrewAI Enterprise** | None at agent level (workflow RBAC only) | Workflow-level roles | Not built-in | SAML/SSO at workspace level |
| **Temporal** | None at agent level | gRPC-level `target:action` | Durable signals + external UI | OAuth/OIDC at gRPC layer |
| **Portkey Gateway** | Per-workspace access control | Per-tool ACLs at gateway | Not built-in | Enterprise IdP integration (RBAC) |
| **Kong AI Gateway** | Consumer groups | Per-tool ACLs (tool ACL plugin) | Not built-in | OIDC, JWT, API key at gateway |

---

## Emerging Standards

| Standard | Status | Relevance |
|----------|--------|-----------|
| **OIDC-A** (OpenID Connect for Agents) | Community proposal, arXiv Sep 2025 | Standard agent identity claims (`model`, `provider`, `instance_id`), delegation chain, capability-based authorization |
| **IETF OBO for AI Agents** | Draft -02, Aug 2025 | Formalizes `actor_token` + OBO for user-delegated agent access |
| **OpenID Foundation: Agentic AI Identity** | Whitepaper Oct 2025 | Identifies gaps: recursive delegation, cross-domain propagation, scope reduction at each hop |
| **Google A2A Protocol** | v0.3 (signed agent cards) | Agent-to-agent auth via signed capability cards; joined by Microsoft, ServiceNow, IBM |
| **W3C DID v1.1** | Spec open for comment Mar 2026 | Self-issued identifiers; research-stage for agents |
| **AgentDID** | arXiv Apr 2026 | DID + Verifiable Credentials for trustless cross-domain agent auth; academic |

**Practical stance**: OIDC-A and IETF OBO are the most likely to reach standards-track maturity in 2026–2027. Cedar and OPA are the viable policy engines today. DID/AgentDID is research-stage; do not design around it.

---

## Implications for Presidium Design

The research confirms the following allocation:

**Presidium provides** (does not delegate to developers):
- Agent identity registry integrated with enterprise IdPs (Entra, Okta, Google IAM, AWS IAM)
- Credential vault: OAuth tokens, API keys, scoped per `(agent_id, user_id)` tuple
- Token exchange service: OBO, XAA/ID-JAG, client credentials on behalf of agents
- MCP OAuth 2.1 authorization (PKCE + Resource Indicators per spec)
- Policy engine (Cedar primary; OPA supported via plugin)
- HITL approval routing with signed payloads (LITL protection) and approver authentication
- Audit aggregation with agent identity + user identity on every event

**Presidium integrates with** (does not implement):
- Enterprise IdPs (Entra, Okta, Auth0, Keycloak, Google, AWS Cognito) — integration, not replacement
- HITL notification channels (Slack, Teams, email) — Presidium handles routing and signed payloads; channel delivery is configurable
- Observability platforms (Fiddler, Arize, Langfuse) — Presidium generates governance telemetry; they dashboard it

**Civitas provides** (the hooks Presidium uses):
- Credential context injection into agent execution (agents receive a token context at startup)
- Durable suspension for HITL (the mechanism: `AgentProcess` awaits a resume signal)
- Audit event emission (what happened, which agent, which message, which tool)
- `RegistryListener` hook (Presidium subscribes to agent lifecycle events)
- Transport security (mTLS between nodes — separate from token-based auth)

See [RFC-001](../rfcs/001-presidium-scope.md) for the formal boundary definition.

---

*Sources: Microsoft Entra Agent ID docs, Google Vertex AI Identity docs, AWS AgentCore docs, LangGraph auth docs, MCP specification (March 2026), Portkey MCP Gateway docs, Kong MCP Tool ACLs blog, Okta XAA announcement and dev guide, IETF OBO draft-02, OpenID Foundation Agentic AI whitepaper, arXiv OIDC-A paper, A2A Protocol specification, Temporal HITL tutorial, Permit.io HITL blog, OWASP LITL attack docs.*
