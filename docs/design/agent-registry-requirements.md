# Agent Registry: Requirements

> What the AgentRegistry must do, informed by [industry research](../research/agent-registry-research.md).
> Status: Draft
> Milestone: M2 (Core Interfaces + CEL Policy)

## Overview

The AgentRegistry is the governance identity store for Presidium. It answers three questions:
1. **Who is this agent?** (identity)
2. **What is this agent allowed to do?** (grants)
3. **How much should we trust this agent?** (trust scoring)

The registry is the source of truth — agents must be registered before they can participate in governed operations. The CEL policy engine reads registry data (grants, trust score, owner) when evaluating policy expressions.

---

## Functional Requirements

### FR-1: Agent Registration

An agent must be registerable with a unique identity that persists across restarts.

**FR-1.1**: The registry MUST accept registration of an agent with at minimum: name (unique string), agent_id (SPIFFE-compatible URI in the format `presidium://{trust_domain}/{path}`), public_key (Ed25519 public key, base64-encoded).
**FR-1.2**: The registry MUST reject registration if the name is already registered.
**FR-1.3**: The registry MUST support optional metadata: owner (string), description (string), agent_version (semver string), capabilities (list of strings).
**FR-1.4**: The registry MUST assign a monotonic revision number to every registration and every subsequent mutation.
**FR-1.5**: The registry MUST support deregistration by name.
**FR-1.6**: The agent_id MUST follow the format `presidium://{trust_domain}/{path}` where trust_domain identifies the governing authority and path encodes the runtime and agent name.
**FR-1.7**: The agent_id for a dynamically spawned child MUST encode the parent's path as a prefix: if parent is `presidium://acme.com/prod/orchestrator`, the child MUST be `presidium://acme.com/prod/orchestrator/child/{child_name}`.
**FR-1.8**: The registry MUST store the agent's Ed25519 public key and use it as the cryptographic binding for identity verification.
**FR-1.9**: The identity format MUST be compatible with the SPIFFE specification (spiffe:// URI scheme, trust domain + hierarchical path) so that a future SPIFFE backend can issue real X.509-SVIDs without changing the URI format.
**FR-1.10**: The `trust_domain` used in agent identity URIs MUST be configurable via the `presidium.registry.trust_domain` topology YAML key (default: `"local"`).

**Scenario**: Agent "researcher" registers at runtime startup with identity `presidium://acme.com/prod/researcher` and its Ed25519 public key. After a crash and supervisor restart, the same agent re-registers with the same identity — the registry verifies the public key matches the existing record and updates it (new revision) rather than creating a duplicate.

**Scenario**: Orchestrator spawns a child agent "worker-3". The child's identity is automatically derived as `presidium://acme.com/prod/orchestrator/child/worker-3`, encoding its lineage in the URI path. No registry lookup is needed to determine parentage.

### FR-2: Grants

Agents hold grants that describe what they are authorized to access. Grants are structured data that CEL policy expressions can evaluate.

**FR-2.1**: A grant MUST contain: resources (list of strings), actions (list of strings).
**FR-2.2**: A grant MAY contain: scope (dict of string→string key-value pairs), condition (CEL expression string), expires_at (datetime).
**FR-2.3**: The registry MUST support adding, removing, and listing grants for an agent.
**FR-2.4**: Grants MUST be accessible in CEL expressions as `agent.grants` — an iterable of grant objects where each grant has `.resources`, `.actions`, `.scope`, `.condition` fields.
**FR-2.5**: Expired grants (where `expires_at < now`) MUST be excluded from policy evaluation.
**FR-2.6**: The `condition` field, when present, MUST be evaluated as a CEL expression at policy evaluation time. A grant with a false condition is treated as not held.

**Scenario**: Agent "analyst" has grant `{resources: ["database"], actions: ["read"], scope: {"environment": "production"}}`. CEL policy: `agent.grants.exists(g, "database" in g.resources && "read" in g.actions)` → evaluates to true.

**Scenario**: Agent "writer" has grant `{resources: ["database"], actions: ["write"], condition: "agent.trust.value >= 0.7"}`. When trust is 0.5, the grant is effectively not held. When trust reaches 0.7, the grant activates. This enables the HITL → autonomy progression.

### FR-3: Trust Scoring

Each agent has a trust score that reflects its behavioral reliability. Trust influences what grants are effective (via conditions) and what tier of access the agent operates in.

**FR-3.1**: Every registered agent MUST have a trust score — a float between 0.0 and 1.0.
**FR-3.2**: The default initial trust score MUST be configurable (default: 0.5).
**FR-3.3**: The trust score MUST be classified into one of 3 tiers:
  - TRUSTED (≥ 0.7): normal operations, all conditional grants active
  - STANDARD (0.3 – 0.7): default operating level, some conditional grants may be inactive
  - RESTRICTED (< 0.3): suspended or sandboxed, human review may be required
**FR-3.4**: The registry MUST support recording trust events: SUCCESS, FAILURE, POLICY_VIOLATION, HUMAN_OVERRIDE.
**FR-3.5**: The trust score MUST be accessible in CEL expressions as `agent.trust.value` (float) and `agent.trust.tier` (string).
**FR-3.6**: Trust scores MUST be durable across agent restarts (persisted to the registry backend).
**FR-3.7**: The TrustScorer MUST be a Protocol — implementations are swappable (LinearTrustScore default, AGT-style AdaptiveTrustScore via contrib).
**FR-3.8**: Every trust event (SUCCESS, FAILURE, POLICY_VIOLATION, HUMAN_OVERRIDE) MUST be persisted with: agent_id, event_type, value_before, value_after, tier_before, tier_after, timestamp. This history is M4 training data for the LearningTrustScorer.

**Scenario**: Agent "processor" processes 100 tasks successfully (100 SUCCESS events). Trust rises from 0.5 to 0.8 (TRUSTED tier). A conditional grant `{condition: "agent.trust.value >= 0.7"}` becomes active.

**Scenario**: Agent "processor" then causes 3 POLICY_VIOLATION events. Trust drops to 0.4 (STANDARD). The conditional grant deactivates. The agent continues operating but with reduced access.

### FR-4: Dynamic Spawning Integration

When agents are spawned dynamically via Civitas's DynamicSupervisor, the registry must enforce governance rules.

**FR-4.1**: A dynamically spawned child agent MUST be registered in the registry before it can participate in governed operations.
**FR-4.2**: A child agent's grants MUST be a strict subset of its parent's grants. The registry MUST reject any spawn that would grant the child permissions the parent does not hold.
**FR-4.3**: A child agent MUST start with the default initial trust score (not inherited from parent).
**FR-4.4**: The registry MUST track lineage: each agent record stores its parent agent_id (None for static agents).
**FR-4.5**: The subset-grant check MUST happen BEFORE spawn (fail-fast), not after.

**Scenario**: Orchestrator agent (grants: ["tool:web_search", "tool:database:read"]) spawns a researcher agent requesting grants: ["tool:web_search"]. Spawn succeeds — subset of parent's grants.

**Scenario**: Orchestrator agent spawns a researcher requesting grants: ["tool:database:write"]. Spawn fails — parent does not hold "tool:database:write".

### FR-5: Lifecycle States

**FR-5.1**: Each agent MUST have a status: REGISTERED, STARTING, RUNNING, STOPPING, STOPPED, SUSPENDED.
**FR-5.2**: The registry MUST support state transitions triggered by Civitas lifecycle hooks (on_start → RUNNING, on_stop → STOPPED).
**FR-5.3**: The SUSPENDED state MUST be enterable when trust drops below a configurable threshold (default: RESTRICTED tier, < 0.3).
**FR-5.4**: Resumption from SUSPENDED MUST require explicit action (human review or API call).
**FR-5.5**: Status MUST be accessible in CEL expressions as `agent.status`.

### FR-6: Querying

**FR-6.1**: The registry MUST support lookup by name (O(1)).
**FR-6.2**: The registry MUST support lookup by agent_id (O(1)).
**FR-6.3**: The registry MUST support listing all agents with optional filters: status, trust tier, owner, capability.
**FR-6.4**: The registry MUST support checking whether a specific grant is held by an agent (for policy evaluation hot path — must be fast).
**FR-6.5**: `lookup()` MUST return an immutable snapshot of the AgentRecord. Grants modified after lookup but before policy evaluation completes MUST NOT affect the in-progress evaluation. The snapshot includes the `revision` number for optimistic concurrency checks.

### FR-7: Persistence

**FR-7.1**: In library mode, the registry MUST support in-memory storage (InMemoryRegistry) and SQLite storage (SqliteRegistry).
**FR-7.2**: In service mode, the registry MUST support Postgres storage (PostgresRegistry via presidium-contrib).
**FR-7.3**: All mutations MUST be atomic with the revision counter increment.
**FR-7.4**: The registry MUST support the StateStore pattern from Civitas — pluggable backends via Protocol.

### FR-8: Authentication

**FR-8.1**: In library mode (same process), the registry MUST trust the runtime — no authentication required.
**FR-8.2**: In service mode, the registry MUST verify agent identity via Civitas message bus signing (Ed25519).
**FR-8.3**: The authentication mechanism MUST be a Protocol (RegistryAuth) — swappable for SPIFFE/JWT in future.

### FR-9: Audit

**FR-9.1**: Every registration, deregistration, grant change, trust score change, and state transition MUST emit an AuditEvent via Civitas's AuditSink.
**FR-9.2**: Audit events MUST include: timestamp, agent_id, event type, old value, new value, actor (who made the change).

---

## Non-Functional Requirements

### NFR-1: Performance
- Grant checking (FR-6.4) MUST complete in < 100 microseconds for in-process evaluation
- Registration MUST complete in < 10 milliseconds (excluding persistence I/O)

### NFR-2: Consistency
- All mutations are atomic with revision increment
- No torn writes during concurrent grant updates (SQLite WAL + BEGIN IMMEDIATE for library mode)

### NFR-3: Availability
- Library mode: available whenever the Python process is running
- Service mode: available whenever the GenServer is running (supervised by Civitas)

### NFR-4: CNCF Standards Alignment
- Agent identity format MUST be compatible with SPIFFE (spiffe:// URI conventions)
- Observability MUST use OpenTelemetry (via Civitas)
- Policy expressions MUST use CEL (Common Expression Language)
- These alignments enable enterprise adoption by ensuring interoperability with existing CNCF-based infrastructure (Kubernetes, Istio, SPIRE, etc.)

---

## Design Decisions (Resolved)

References to the rationale behind each decision. Full analysis in [agent-registry.md](agent-registry.md).

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Grant grammar | K8s-style structured grants with CEL condition field | Expressive enough for HITL→autonomy, simple enough for developers, evolvable toward ReBAC |
| D2 | Human sponsor | Schema-optional, policy-enforced (permissive in library mode, required in service mode via CEL) | Keeps registry as data model, policy engine enforces rules, same schema for dev and enterprise |
| D3 | Trust scoring | 0.0-1.0 float, 3 tiers (TRUSTED/STANDARD/RESTRICTED), Protocol for swapping implementations | Ships simple, Protocol allows AGT-style upgrade via contrib |
| D4 | Spawning inheritance | Subset grants (enforced), independent trust (not inherited), lineage tracked | Prevents privilege escalation and trust laundering |
| D5 | Versioning | Revision counter on mutations + optional agent_version metadata | Audit needs revisions, app versioning is metadata |
| D6 | Credentials | Trust-the-runtime (library) + message-bus-signing (service), Protocol for future SPIFFE | Minimal ceremony for M2, clean upgrade path |
| D7 | Agent identity format | SPIFFE-compatible URI (`presidium://`) with Ed25519 binding | Aligns with CNCF standards, encodes trust domain and lineage, self-describing, upgradeable to real SPIFFE SVIDs |

---

## Out of Scope (M2)

- Trust contagion / network propagation (M4)
- KL divergence regime detection (M4)
- Zanzibar-style ReBAC / tuple store (M3+)
- SPIFFE/JWT-SVID credentials (M3+)
- Historical state queries by revision (M3)
- Agent groups / teams with shared grants (M3)
- Delegation depth limits (M3)
- Cross-deployment federation (M4+)
- Real SPIFFE SVID issuance via SPIRE (M3+ — `presidium-contrib[spiffe]`)
