# Policy Engine: Requirements

> What the PolicyEngine must do, informed by [industry research](../research/agent-registry-research.md) and [policy engine research](/Users/jeryn/workspace/projects/policy-engines-ai-governance/index.md).
> Status: Draft
> Milestone: M2 (Core Interfaces + CEL Policy)

## Overview

The PolicyEngine is the enforcement layer for Presidium. It evaluates CEL expressions against an EvaluationContext (containing agent identity, grants, trust score, and the action being attempted) and returns a decision: ALLOW, DENY, or REQUIRE_APPROVAL.

The policy engine follows the PDP/PEP/PIP architecture pattern:
- **PDP (Policy Decision Point)**: `PolicyEngine` — evaluates expressions, returns decisions
- **PEP (Policy Enforcement Point)**: `GovernedModelProvider`, `GovernedToolProvider` — intercept actions, call the PDP, enforce the decision
- **PIP (Policy Information Point)**: `AgentRegistry` — provides agent identity, grants, and trust score to the evaluation context

---

## Functional Requirements

### FR-1: Policy Definition

**FR-1.1**: A policy rule MUST contain: name (string), stage (evaluation stage), expression (CEL string), decision (ALLOW/DENY/REQUIRE_APPROVAL).
**FR-1.2**: A policy rule MAY contain: description, reason (string returned on match), priority (int, higher = evaluated first), approvers (list of strings for REQUIRE_APPROVAL), enabled (bool).
**FR-1.3**: Policies MUST be loadable from YAML configuration (topology file or standalone policy file).
**FR-1.4**: The policy engine MUST compile CEL expressions at load time and report compilation errors immediately (fail-fast on bad policy).
**FR-1.5**: The policy engine MUST support loading multiple policy files that are merged at evaluation time.

**Scenario**: A YAML policy file defines 3 rules — grant enforcement (priority 100), trust-gated write access (priority 90), and owner requirement for registration (priority 80). All three are compiled at startup. A typo in a CEL expression (`agent.grrants` instead of `agent.grants`) fails compilation immediately with a clear error message.

### FR-2: Evaluation Context

**FR-2.1**: The evaluation context MUST contain: `agent` (AgentRecord — name, agent_id, grants, trust, status, owner), `request` (what is being attempted — resource, action, parameters), `time` (current timestamp).
**FR-2.2**: Grants on the agent record MUST be accessible as `agent.grants` — an iterable of Grant objects with `.resources`, `.actions`, `.scope`, `.condition` fields.
**FR-2.3**: Trust MUST be accessible as `agent.trust.value` (float 0.0-1.0) and `agent.trust.tier` (string: "trusted"/"standard"/"restricted").
**FR-2.4**: The context MUST be extensible — custom fields can be added without changing the Protocol.

**Scenario**: Agent "researcher" with trust 0.6 attempts to call tool "database" with action "write". The evaluation context is: `{agent: {name: "researcher", trust: {value: 0.6, tier: "standard"}, grants: [...], status: "running"}, request: {resource: "tool:database", action: "write"}, time: "2026-06-11T10:00:00Z"}`.

### FR-3: Evaluation Stages

**FR-3.1**: The policy engine MUST support evaluation at these stages:
  - `pre_tool`: before a tool call is executed
  - `pre_llm`: before an LLM call is made
  - `registration`: when an agent attempts to register

`pre_message` (before sending a message to another agent) is deferred to M3 — it requires a Civitas MessageBus hook that is outside the 2 minimal Civitas changes in M2.
**FR-3.2**: Only policies matching the current stage MUST be evaluated (e.g., pre_tool policies are skipped during LLM calls).
**FR-3.3**: Within a stage, policies MUST be evaluated in priority order (highest first).
**FR-3.4**: First matching expression determines the decision (first-match-wins).
**FR-3.5**: If no expression matches, the default decision MUST be ALLOW (the absence of a matching deny/require_approval rule means no policy objects).
**FR-3.6**: A PolicyRule MAY specify multiple stages as a list (e.g., `stage: [pre_tool, pre_llm]`). The rule MUST be evaluated at each listed stage. This avoids duplicating identical rules across stages.

Note on FR-3.5: This is NOT "default allow" in the security sense. The standard deployment includes a grant-enforcement policy at priority 100 that denies any action the agent doesn't have a grant for. "No expression matches" means all policies passed — including the grant check. Users who want explicit default-deny add a catch-all deny rule at priority 0.

### FR-4: Fail-Closed Evaluation

**FR-4.1**: If a CEL expression fails to evaluate (runtime error, missing field, type mismatch), the result MUST be DENY.
**FR-4.2**: Evaluation errors MUST be logged with the expression name, error details, and the context that caused the failure.
**FR-4.3**: The fail-closed behavior MUST NOT be configurable — it is a security invariant.

**Scenario**: A policy expression references `agent.metadata.custom_field` but the agent's metadata doesn't contain that field. The CEL evaluation throws an error. The policy engine returns DENY and logs the error. The agent's action is blocked.

### FR-5: Policy Decisions

**FR-5.1**: The `PolicyResult` MUST contain: decision (ALLOW/DENY/REQUIRE_APPROVAL), policy_name (which rule matched, or None if no rule matched), reason (human-readable explanation).
**FR-5.2**: For REQUIRE_APPROVAL decisions, the result MUST include approvers (list of strings — email addresses or role identifiers).
**FR-5.3**: For DENY decisions, the result MUST include the reason from the policy rule.
**FR-5.4**: Every policy evaluation MUST emit an AuditEvent via Civitas's AuditSink, including: stage, decision, policy_name, agent_id, resource, action, evaluation time.

### FR-6: Enforcement Points (PEPs)

**FR-6.1**: `GovernedModelProvider` MUST evaluate `pre_llm` policies before delegating to the underlying `ModelProvider`.
**FR-6.2**: `GovernedToolProvider` MUST evaluate `pre_tool` policies before delegating to the underlying `ToolProvider`.
**FR-6.3**: On DENY, the PEP MUST raise a `PolicyDeniedError` (not silently swallow the action).
**FR-6.4**: On REQUIRE_APPROVAL, the PEP MUST route to the `ApprovalService` and await a decision before proceeding.
**FR-6.5**: On ALLOW, the PEP MUST delegate to the underlying provider and return the result unchanged.

### FR-7: Grant-Policy Integration

**FR-7.1**: The standard grant-enforcement policy MUST be a built-in default rule that checks `agent.grants.exists(g, request.resource in g.resources && request.action in g.actions)`.
**FR-7.2**: Grant conditions (the `condition` field on Grant) MUST be evaluated as part of the grant check — a grant with a false condition is treated as not held.
**FR-7.3**: Expired grants (where `expires_at < now`) MUST be filtered out before policy evaluation.
**FR-7.4**: The grant enforcement policy MUST be removable — users who want custom grant logic can replace it with their own expression.

### FR-8: Enforcement Modes

**FR-8.1**: The policy engine MUST support three enforcement modes: `advisory` (log only, never block), `soft` (log and warn but don't block), `hard` (enforce — block on DENY).
**FR-8.2**: The enforcement mode MUST be configurable per-policy (not just globally).
**FR-8.3**: In advisory mode, the policy result MUST still be computed and logged — only the enforcement is skipped.

**Scenario**: A new policy "restrict-expensive-models" is deployed in advisory mode for 48 hours. During this time, the policy engine evaluates it on every LLM call and logs what would have been blocked. After review confirms no false positives, the mode is changed to hard enforcement via a topology YAML change.

### FR-9: Protocol and Extensibility

**FR-9.1**: `PolicyEngine` MUST be a Protocol — implementations are swappable.
**FR-9.2**: `CelPolicyEngine` MUST be the default implementation in the `presidium` core package.
**FR-9.3**: `OpaPolicyEngine` and `CedarPolicyEngine` MUST be available as adapters in `presidium-contrib`.

---

## Non-Functional Requirements

### NFR-1: Performance
- CEL expression evaluation MUST complete in < 5 milliseconds per policy rule (cel-python typical: 1-3ms)
- Full policy evaluation (all matching rules for a stage) MUST complete in < 20 milliseconds
- CEL expressions MUST be compiled once at load time, not per-evaluation

### NFR-2: Safety
- CEL is non-Turing-complete — guaranteed termination, no infinite loops
- CEL is side-effect-free — no I/O, no network calls, no state mutation during evaluation
- No sandboxing overhead — the language itself is the constraint

### NFR-3: Determinism
- Same input MUST produce the same output on every evaluation
- Policy evaluation MUST NOT depend on external state fetched during evaluation (all data in the context)

### NFR-4: CNCF Alignment
- CEL is the CNCF-aligned policy expression language (Kubernetes, Envoy, Google Cloud)
- OTEL audit spans for every policy decision (via Civitas AuditSink)
- OPA adapter aligns with CNCF graduated policy engine

---

## Design Decisions (Resolved)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| P1 | Policy language | CEL (default), OPA/Cedar as contrib adapters | CEL is embeddable (in-process, 1-3ms in Python), CNCF-aligned, non-Turing-complete (safe for untrusted expressions). OPA for teams with existing Rego policies. |
| P2 | Evaluation model | First-match-wins by priority, per-stage | Simple, deterministic, matches AGT's approach. Priority ordering gives operators clear control. |
| P3 | Fail-closed | CEL errors → DENY (non-configurable) | Security invariant from AGT research. Prevents exception-based policy bypass. |
| P4 | Enforcement modes | advisory/soft/hard per-policy | Enables gradual rollout without risk. Advisory mode is critical for policy testing in production. From policy lifecycle pipeline pattern. |
| P5 | Default behavior | No matching rule → ALLOW (grant policy at priority 100 provides the deny) | Keeps the engine generic. Grant enforcement is a policy, not engine logic. Users control the default via policy rules. |
| P6 | Grant integration | Grants are data the engine reads, not logic the engine executes | Clean separation: grants are on AgentRecord, policies evaluate grants. Don't conflate. |

---

## Out of Scope (M2)

- OPA adapter (M3 — `presidium-contrib[opa]`)
- Cedar adapter (M3 — `presidium-contrib[cedar]`)
- Rate limiting in policies (needs stateful counter — M3)
- Policy hot-reload without restart (M3)
- Post-execution stages (post_tool, post_llm — M3)
- Policy composition / inheritance from agent groups (M3)
- LLM-based policy evaluation (content safety is Fiddler/guardrails, not Presidium)
- Formal verification of policies (Cedar-specific, M3+)
