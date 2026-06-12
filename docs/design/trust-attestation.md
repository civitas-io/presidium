# Trust Attestation Design

> Status: Design proposal — not yet implemented.
> Target: presidium-registry v1 + presidium-policy v1

---

## The Problem with Binary Trust

Treating agent trust as a single `trusted/not trusted` bit is insufficient. An agent can be
in any of these states simultaneously:

- Cryptographically verified (valid identity key) but operating with expired delegation
- Valid identity + current authority but not actively responding (silent agent)
- All three valid but operating under a stale policy version

Conflating these causes either **over-revocation** (killing a healthy agent on timeout) or
**under-revocation** (continuing to trust a silent agent because its key is still valid).

---

## Three-Tier Attestation Model

Agent trust decomposes into three **independently-decaying** attestation properties:

| Property | What it represents | Decay model |
|---|---|---|
| **Identity** | Cryptographic binding (public key / DID) | Slow — explicit key rotation only |
| **Authority** | Scope of what this agent is permitted to do | TTL-based — re-attest on expiry |
| **Liveness** | Proof that the agent is still the agent | Fast — heartbeat-driven, minutes-scale |

An agent may exercise its authority **only when all three attestations are valid**.

### Liveness: Suspension vs Revocation

A liveness failure (missed heartbeats) causes **suspension** — a reversible state.
Suspension is not revocation:

- A suspended agent's grants remain intact
- Restoration requires re-establishing liveness (heartbeat ack + delegation chain verification)
- Revocation (identity or authority level) is a separate, deliberate administrative action

This distinction matters in practice: a transient network partition or a supervisor restart
should cause suspension + automatic restoration, not permanent revocation of the agent's
grants.

### Mapping to Civitas

Civitas's supervision model already tracks these properties implicitly:

| Attestation property | Civitas concept |
|---|---|
| Identity | `Registry` name + (future) public key on `AgentRecord` |
| Authority | `AgentRecord.grants` (Presidium) |
| Liveness | `Supervisor` heartbeat (`_agency.heartbeat` / `_agency.heartbeat_ack`), `ProcessStatus` |

Presidium's `RegistryListener` subscribes to supervisor lifecycle events — a crashed or
unresponsive agent maps to liveness failure → suspension. The `RegistryListener.on_agent_crash()`
hook is the natural integration point.

### Proposed AgentRecord Fields

```python
@dataclass
class AgentRecord:
    agent_id: str
    name: str
    owner: str
    capabilities: list[str]      # Civitas routing tags
    grants: list[str]            # Presidium authorization entitlements
    trust_score: float           # 0.0–1.0

    # Three-tier attestation
    identity_key: str | None         # Ed25519 public key (future: DID)
    authority_expires_at: float | None   # epoch — None means indefinite
    liveness_last_seen: float            # epoch of last successful heartbeat_ack
    liveness_status: Literal["active", "suspended", "revoked"] = "active"
```

---

## Policy Version Attestation

Beyond agent-level trust, policy enforcement requires that agents are operating against a
current (not stale) policy version. Two cases with different propagation semantics:

**Policy tightening (removes or restricts a capability):**
Must propagate immediately. An agent holding a stale policy cache cannot exercise a
newly-revoked capability. On receiving a tightening update, `GovernedToolProvider` and
`GovernedModelProvider` must re-fetch policy before the next action.

**Policy loosening (adds or expands a capability):**
Propagation can follow normal TTL expiry. There is no security risk in an agent not yet
knowing about a new capability it hasn't used.

Implementation: `PolicyEngine.publish_update()` sets `min_valid_policy_version` atomically
on tightening updates. Any policy check presenting a version below the minimum is rejected
with a re-fetch directive before the action can proceed.

---

## Intent Declaration

Registering per-action policies governs each action in isolation. It cannot detect when a
sequence of individually-compliant actions collectively drifts from the agent's declared goal.

A session-level **intent declaration** complements per-action policy by giving the governance
layer visibility into what the agent *intends to do before it starts*:

- The agent sends a structured plan at task start: which tools it expects to call, with what
  parameter constraints, and within what time window
- The governance layer validates each subsequent tool call against the registered plan
- An unplanned tool call triggers a configurable response: warn, block, or require re-declaration

This catches goal-hijacking that per-action rules miss: an agent with ALLOW on both
`read_email` and `send_email` that starts forwarding emails instead of summarizing them is
violating its declared intent without violating any per-action rule.

In Civitas's message-passing model, intent declaration is a message type sent to the
Presidium policy agent before the task begins. The policy agent maintains a per-task plan
registry and validates tool calls against it via `GovernedToolProvider`.

---

## Policy Conflict Resolution

When multiple policies apply to a single action (e.g., a global default and an agent-specific
override), a conflict resolution strategy determines which takes precedence.

This should be a **named, configurable deployment parameter**, not hardcoded logic:

| Strategy | Semantics |
|---|---|
| `DENY_OVERRIDES` | Any policy that denies wins, regardless of other policies |
| `ALLOW_OVERRIDES` | Any policy that allows wins |
| `PRIORITY_FIRST_MATCH` | Policies evaluated in priority order; first match wins |
| `MOST_SPECIFIC_WINS` | Narrowest scope (agent > org > tenant > global) wins |

**Default: `DENY_OVERRIDES`.** This is the secure default — an explicit deny at any scope
cannot be accidentally overridden by a broader allow.

Scope hierarchy (narrowest wins in MOST_SPECIFIC): global < tenant < organization < agent.

The `PolicyEngine.evaluate()` interface is identical regardless of strategy — strategy is an
implementation detail injected at construction time. This allows different deployments to
choose their own conflict semantics without changing application code.
