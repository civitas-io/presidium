# Design Inspiration from AGT Analysis

> Source: Analysis of microsoft/agent-governance-toolkit (MIT license), 2026-05-06
> **IP note:** AGT is MIT-licensed. These are design ideas derived from reading and
> understanding their architecture. No AGT code is copied here. Implementations
> must be independently written in our own style against our own interfaces.

This doc captures AGT design concepts worth incorporating into Presidium's design,
translated into the OTP/Civitas mental model. Each section explains the original
concept, why it's sound, and how it fits our architecture.

---

## 1. Three-Tier Trust Decomposition

### What AGT does

ADR-0005 decomposes agent trust into three independently-decaying properties:

| Property | What it represents | Decay model |
|---|---|---|
| **Identity** | Cryptographic public key (DID) | Very slow — key rotation only |
| **Authority** | Delegation scope (what the agent is permitted to do) | TTL-based — re-attest on expiry |
| **Liveness** | Heartbeat verification (agent is still the agent) | Fast — minutes-scale |

An agent exercises authority **only when all three validate simultaneously**.
Liveness failure causes **suspension** (reversible), not revocation.
Restoration: verify delegation chain hash, re-emit liveness proof.

### Why this is sound

Current Presidium design treats trust as a binary `trusted/not trusted` bit on the
`AgentRecord`. That's insufficient:
- An agent with a valid key may have stale/expired authority (delegation TTL expired)
- An agent with valid key and current authority may have gone silent (liveness failure)
- Conflating these three causes either over-revocation (kill a healthy agent on timeout)
  or under-revocation (continue trusting a silent agent)

### Civitas/Presidium translation

Civitas already has the three properties — they just aren't modeled as trust attestations:

| AGT property | Civitas concept | Where it lives |
|---|---|---|
| Identity | Agent's registered name + public key | Civitas `Registry` + Presidium `AgentRecord` |
| Authority | Declared capabilities + grants | Presidium `AgentRecord.grants` |
| Liveness | Supervisor heartbeat protocol (`_agency.heartbeat` / `_agency.heartbeat_ack`) | Civitas `Supervisor` |

**Proposed change:** Add three attestation fields to `AgentRecord`:
```python
@dataclass
class AgentRecord:
    agent_id: str
    # ... existing fields ...
    identity_key: str                    # Ed25519 public key (DID or similar)
    authority_expires_at: float | None   # TTL for current grant set; None = indefinite
    liveness_last_seen: float            # Timestamp of last heartbeat_ack
    liveness_status: Literal["active", "suspended", "revoked"]
```

Suspension on missed heartbeat maps naturally to `ProcessStatus.CRASHED` in Civitas — the
supervisor already has this state. Presidium should subscribe to supervisor crash events
via `RegistryListener` and update `liveness_status` accordingly.

---

## 2. Intent Declaration + Drift Detection

### What AGT does

Agents declare a plan before executing: `planned_actions = [{name, parameter_constraints}]`.
Every actual tool call is checked against that manifest. Unplanned actions trigger a
configurable `DriftPolicy`:

- `soft_block` — warn and continue
- `hard_block` — deny the action
- `re_declare` — force agent to re-declare its plan

### Why this is sound

Per-action policy (ALLOW/DENY on individual tool calls) only validates each action in
isolation. It cannot detect when a sequence of individually-compliant actions collectively
drifts from the original goal — a subtler and often more dangerous failure mode than
individual policy violations.

Example: an agent with ALLOW on `read_email` and ALLOW on `send_email` that was tasked
with "summarize my inbox" but starts sequentially reading emails and forwarding each one
is violating its intent without violating any per-action rule.

### Civitas/Presidium translation

In Civitas's message-passing model, intent declaration is a message type:

```python
# Agent sends this before starting a task
Message(
    type="presidium.intent.declare",
    sender=agent_name,
    recipient="presidium.policy",
    payload={
        "task_id": "task-uuid",
        "declared_actions": [
            {"tool": "read_email", "max_calls": 50, "target": "inbox"},
            {"tool": "call_llm", "max_calls": 10},
        ],
        "declared_ttl": 300,  # seconds — plan expires if not completed
    }
)
```

The presidium policy agent validates each subsequent tool call against the registered plan
for that `task_id`. Unregistered tool calls → `DriftPolicy` enforcement.

**Implementation hook:** `presidium-policy` intercepts `ToolProvider.execute()` calls via
Civitas's `GovernedToolProvider` wrapper, checks them against the active plan for the
calling agent's current `task_id`.

**Key design decision:** drift detection is at the *session* level, not the *action* level.
The plan is registered once per task, not per message.

---

## 3. Context Budget as a Governance Primitive

### What AGT does

Models LLM token allocation as OS CPU scheduling:
- A global `ContextPool` of total tokens available across all agents
- Per-agent `ContextWindow` allocations requested at task start
- Enforced 90%/10% lookup/reasoning split within each allocation
- Typed signals: `SIGWARN` (approaching limit), `SIGSTOP` (over limit), `SIGRESUME` (quota restored)
- `BudgetExceeded` exception on overrun, triggering policy callback

### Why this is sound

Token cost is the primary operational cost driver for agentic systems. Without budget
enforcement at the governance layer, a single runaway agent can consume the entire
organization's monthly LLM budget in minutes. This is the "blast radius controller" problem
applied to LLM economics.

The OS scheduling analogy is the right mental model: just as an OS limits per-process CPU
time to prevent starvation, a governance layer limits per-agent token consumption.

### Civitas/Presidium translation

**In the LLM gateway (`presidium-llm-gateway`):**

```python
@dataclass
class ContextBudget:
    agent_id: str
    max_tokens_per_task: int
    max_tokens_per_day: int
    lookup_ratio: float = 0.90   # target: 90% retrieval, 10% reasoning
    current_task_usage: int = 0
    daily_usage: int = 0

class GovernedModelProvider:
    async def chat(self, model, messages, *, agent_id, task_id, **kwargs):
        budget = await self._registry.get_budget(agent_id)
        await self._check_budget(budget, estimated_tokens)
        response = await self._underlying.chat(model, messages, **kwargs)
        await self._record_usage(budget, response.tokens_in + response.tokens_out)
        return response
```

The `SIGSTOP` analogue: when budget is exceeded, `GovernedModelProvider` raises
`BudgetExceeded`, which triggers an `ErrorAction.STOP` at the `AgentProcess` level.

**Fields to add to `AgentRecord`:**
```python
context_budget: ContextBudget | None   # None = unlimited
```

---

## 4. Asymmetric Policy-Change Propagation

### What AGT does

ADR-0008: when a policy update removes a capability, it propagates immediately
(returns `412 Precondition Failed` on stale cache). When it adds a capability,
propagation respects normal TTL expiry.

```
Tighten policy → immediate invalidation → agents cannot exercise revoked capability
Loosen policy  → TTL-based propagation → agents cannot exercise new capability yet
```

The security invariant: the "fail open" direction (policy loosening) is always safe
to delay. The "fail closed" direction (policy tightening) must be immediate.

### Civitas/Presidium translation

When `presidium-policy` publishes a policy update:

```python
async def publish_policy_update(self, update: PolicyUpdate) -> None:
    if update.removes_capabilities:
        # Broadcast immediately — all agents must re-validate
        await self._bus.broadcast(
            "presidium.policy.updated",
            {"version": update.version, "invalidate_cache": True}
        )
        # Return 412 on any policy check using old version
        self._min_valid_version = update.version
    else:
        # Schedule propagation at normal TTL
        await self._schedule_propagation(update, delay=self._policy_ttl)
```

`GovernedModelProvider` and `GovernedToolProvider` include their cached policy version
in each call. If `cached_version < min_valid_version`, the call is rejected with a
clear error asking the agent to re-fetch policy before retrying.

---

## 5. Named Policy Conflict Resolution Strategies

### What AGT does

When multiple policies apply to an action, a named conflict resolution strategy determines
the winner:

| Strategy | Semantics |
|---|---|
| `DENY_OVERRIDES` | Any policy that denies wins, regardless of other policies |
| `ALLOW_OVERRIDES` | Any policy that allows wins |
| `PRIORITY_FIRST_MATCH` | Policies evaluated in priority order; first match wins |
| `MOST_SPECIFIC_WINS` | Most specific scope (AGENT > ORG > TENANT > GLOBAL) wins |

Scope hierarchy (narrowest wins in MOST_SPECIFIC): GLOBAL < TENANT < ORGANIZATION < AGENT.

Default: `DENY_OVERRIDES` — the secure default.

### Why this is important

Presidium's policy engine must make this decision. Hardcoding `DENY_OVERRIDES` is safe but
inflexible — some deployments may need `MOST_SPECIFIC_WINS` to allow tenant-level overrides
of global defaults.

### Civitas/Presidium translation

Make it a configurable deployment parameter:

```yaml
# presidium.yaml
policy:
  conflict_resolution: DENY_OVERRIDES   # DENY_OVERRIDES | MOST_SPECIFIC_WINS | PRIORITY_FIRST_MATCH
  scope_hierarchy:
    - global
    - tenant
    - organization
    - agent
```

The `PolicyEngine.evaluate()` interface is the same regardless of strategy — strategy is
an implementation detail. This allows enterprises to choose their own conflict semantics
without changing application code.

---

## 6. Folder-Scoped Hierarchical Policy Discovery

### What AGT does

`PolicyEvaluator._evaluate_scoped()` walks the filesystem from an action's path up to a
configured root, loading `governance.yaml` at each level and merging them.

Invariant: **parent `deny` rules cannot be overridden by children.** A child `override=True`
on a deny is silently ignored, preserving the security invariant.

### Relevance to Presidium

Useful if Presidium governs coding agents or CI/CD agents that operate within a repository
structure. A Presidium-governed coding agent could be subject to:

```
/repo/                        ← global repo policy (deny write to .env)
  /src/                       ← source policy (allow read, deny delete)
    /src/auth/                ← auth module policy (deny LLM-generated crypto code)
```

Without this, Presidium would need a separate policy rule for every path pattern.
Hierarchical discovery lets the filesystem structure be the policy namespace.

**Implementation:** When `GovernedToolProvider` intercepts a file operation, it resolves
the path to a policy scope by walking up to the repo root and merging `governance.yaml`
files found along the way. Parent denies take precedence.

---

## Summary: What to Build vs. Defer

| Idea | Presidium phase | Complexity |
|---|---|---|
| Three-tier trust (fields on AgentRecord) | Registry v1 | Low — just schema |
| Three-tier trust (liveness enforcement) | Post-registry | Medium |
| Named conflict resolution strategy | Policy engine v1 | Low — design decision |
| Asymmetric propagation | Policy engine v1 | Low — routing logic |
| Context budget (fields + basic tracking) | LLM gateway v1 | Medium |
| Context budget (signals, lookup/reasoning split) | LLM gateway v2 | High |
| Intent declaration + basic drift check | Policy engine v2 | High |
| Folder-scoped policy discovery | Policy engine v2 | Medium |
