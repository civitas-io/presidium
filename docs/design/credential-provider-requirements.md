# Credential Provider: Requirements

> What the CredentialProvider must do, informed by credential management research across Vault, AWS Secrets Manager, Infisical, Doppler, and existing Civitas credential infrastructure.
> Status: Draft
> Milestone: M2 (Core Interfaces + CEL Policy)

## Overview

The CredentialProvider manages per-agent secret access with governance context. It sits between agents and their credentials, enforcing grant-based access control and producing audit trails.

Civitas already provides the plumbing: `SecretsProvider` protocol, per-agent `credentials:` block in topology YAML, `agent._credentials` dict, `get_credential()` and `model_for()` methods, and `secret.access` audit events. Presidium's CredentialProvider adds the governance layer: grant-based scoping, backend abstraction, and enriched audit.

Key finding from research: **no major agent framework (LangChain, CrewAI, AutoGen) has built-in credential isolation.** All rely on environment variables with no per-agent scoping, no audit trail, and no rotation. This is a genuine gap.

---

## Functional Requirements

### FR-1: Credential Resolution

**FR-1.1**: The CredentialProvider MUST resolve a credential given an agent identity and a provider/secret name.
**FR-1.2**: The CredentialProvider MUST check that the agent holds a grant authorizing access to the requested credential before returning it. If no grant exists, the request MUST be denied.
**FR-1.3**: The grant check MUST use the same grant model as the AgentRegistry — `agent.grants.exists(g, "credential:{name}" in g.resources && "read" in g.actions)`.
**FR-1.4**: Denied credential requests MUST emit an audit event with the denial reason.

**Scenario**: Agent "researcher" with grant `{resources: ["credential:anthropic"], actions: ["read"]}` calls `get_credential("anthropic")`. The CredentialProvider checks the grant, finds a match, resolves the credential from the backend, and returns it. An audit event records the access.

**Scenario**: Agent "researcher" calls `get_credential("openai")`. The CredentialProvider checks grants, finds no matching grant for `credential:openai`, returns None, and emits an audit event with reason "no grant for credential:openai".

### FR-2: Backend Abstraction

**FR-2.1**: The CredentialProvider MUST be a Protocol — backends are swappable.
**FR-2.2**: The `presidium` core package MUST include `EnvCredentialProvider` (reads from `os.environ`) and `FileCredentialProvider` (reads from key=value files) as default implementations. These wrap Civitas's existing `SecretsProvider` implementations.
**FR-2.3**: `presidium-contrib` MUST support Vault (`presidium-contrib[vault]`), AWS Secrets Manager (`presidium-contrib[aws]`), and Infisical (`presidium-contrib[infisical]`) as adapter implementations.
**FR-2.4**: All backends MUST implement the same Protocol — agents don't know which backend is in use.

### FR-3: Civitas Integration

**FR-3.1**: The CredentialProvider MUST populate `agent._credentials` at runtime startup, replacing the raw YAML credential values with governance-checked resolution.
**FR-3.2**: Agents MUST continue to use `self.get_credential(provider_name)` and `self.model_for(provider_name)` unchanged — the governance layer is transparent.
**FR-3.3**: The CredentialProvider MUST work with Civitas's existing `${VAR_NAME}` substitution — env var references in topology YAML are resolved before the CredentialProvider sees them.
**FR-3.4**: The CredentialProvider MUST integrate with the topology YAML via a `presidium.credentials` block.

### FR-4: Audit

**FR-4.1**: Every credential access (successful or denied) MUST emit an AuditEvent via Civitas's AuditSink.
**FR-4.2**: Audit events MUST include: agent_id, credential name, access result (granted/denied), grant that authorized access (if granted), denial reason (if denied), timestamp.
**FR-4.3**: Audit events MUST be enriched with governance context beyond what Civitas's `secret.access` event provides — specifically, which grant authorized the access and the agent's trust tier at the time of access.

### FR-5: Token Lifecycle (Service Mode)

**FR-5.1**: For backends that support token-based access (Vault, Infisical), the CredentialProvider MUST handle token renewal transparently — agents should not need to manage tokens.
**FR-5.2**: Token TTL and renewal MUST be configurable per-backend in topology YAML.
**FR-5.3**: Token renewal failures MUST be logged but MUST NOT crash the agent — fall back to cached credential if available, log a warning, retry on next access.

### FR-6: Credential Scoping

**FR-6.1**: Credentials MUST be scoped per-agent — agent A cannot access agent B's credentials even if both use the same backend.
**FR-6.2**: For dynamically spawned agents, credential access MUST follow the subset grant rule — a child agent can only access credentials its parent has grants for.
**FR-6.3**: The CredentialProvider MUST support environment-based scoping — same agent name can resolve different credentials in dev vs staging vs production based on topology configuration.

---

## Non-Functional Requirements

### NFR-1: Performance
- Credential resolution from env/file backends MUST complete in < 1ms
- Credential resolution from Vault/AWS backends MUST complete in < 100ms (network I/O bound)
- Credential caching SHOULD be supported for remote backends with configurable TTL

### NFR-2: Security
- Credential values MUST NOT appear in log output or audit events (log the access, not the value)
- Credential values MUST NOT be stored in plain text in the registry or state store
- The CredentialProvider MUST NOT cache credentials longer than the backend's TTL

### NFR-3: Availability
- Library mode: available whenever the Python process is running
- Service mode: remote backend unavailability MUST NOT crash agents — use cached values with warnings

---

## Design Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| C1 | Grant-based access | Credentials are resources in the grant model (`credential:{name}`) | Unified authorization — same grant system for tools, LLMs, and credentials |
| C2 | Backend abstraction | Protocol with env/file defaults, Vault/AWS/Infisical as contrib | Same pattern as PolicyEngine (CEL default, OPA contrib) and AgentRegistry (InMemory default, Postgres contrib) |
| C3 | Civitas integration | Populate `agent._credentials` at startup, agents use existing API | Zero changes to Civitas core or agent code. Governance is transparent. |
| C4 | Token lifecycle | Transparent renewal in remote backends | Agents shouldn't manage tokens — infrastructure concern |
| C5 | Audit enrichment | Add grant context to Civitas's existing `secret.access` events | Enriched audit without duplicating the audit pipeline |

---

## Out of Scope (M2)

- OAuth token exchange (OBO, XAA) — M3+ (requires IdP integration)
- Dynamic secret generation (Vault database engine) — M3+
- Credential rotation automation — M3+
- Cross-deployment credential federation — M4+
- Secret versioning and rollback — M3+
