# Design: Policy Engine

> Deterministic policy evaluation for agent governance.

**Status:** Draft (revised June 2026)
**Package:** `presidium` (protocol + CelPolicyEngine) / `presidium-contrib` (OPA, Cedar adapters)
**Milestone:** M2
**Requirements:** [policy-engine-requirements.md](policy-engine-requirements.md)
**Research:** [agent-registry-research.md](../research/agent-registry-research.md), [policy-engines-ai-governance](/Users/jeryn/workspace/projects/policy-engines-ai-governance/index.md)

## Problem Statement

Agent systems lack deterministic policy enforcement. Agents can call any tool, access any data, invoke any LLM — with no constraints beyond what the framework allows. Guardrails (Fiddler, NeMo) address content safety but not structural governance: "Is this agent authorized to perform this action?"

## Goals

1. Deterministic, sub-5ms policy evaluation using CEL (Common Expression Language)
2. Three decision types: ALLOW, DENY, REQUIRE_APPROVAL
3. Policies evaluate against the AgentRecord (grants, trust, status, owner)
4. Fail-closed on evaluation errors (security invariant)
5. Gradual rollout via enforcement modes (advisory → soft → hard)
6. The PolicyEngine is a Protocol — CEL default, OPA/Cedar via contrib adapters

## Non-Goals (M2)

- Content safety / hallucination detection (that's Fiddler/guardrails)
- LLM output filtering (content layer, not policy layer)
- Rate limiting (needs stateful counters — M3)
- Policy hot-reload without restart (M3)
- Formal verification (Cedar-specific — M3+)

---

## Architecture: PDP / PEP / PIP

The policy engine follows the standard authorization architecture:

| Component | Role | Presidium Implementation |
|---|---|---|
| **PDP** (Policy Decision Point) | Evaluates expressions, returns decisions | `PolicyEngine` / `CelPolicyEngine` |
| **PEP** (Policy Enforcement Point) | Intercepts actions, calls PDP, enforces | `GovernedModelProvider`, `GovernedToolProvider` |
| **PIP** (Policy Information Point) | Provides agent context for evaluation | `AgentRegistry` (grants, trust, identity) |

```
Agent calls tool
    ↓
GovernedToolProvider (PEP)
    ↓ builds EvaluationContext
    ↓ calls PolicyEngine.evaluate()
PolicyEngine (PDP)
    ↓ loads agent data from AgentRegistry (PIP)
    ↓ evaluates CEL expressions against context
    ↓ returns PolicyResult
GovernedToolProvider
    ↓ ALLOW → delegate to underlying ToolProvider
    ↓ DENY → raise PolicyDeniedError
    ↓ REQUIRE_APPROVAL → route to ApprovalService
```

---

## Data Model

### PolicyRule

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"

class EvaluationStage(Enum):
    PRE_TOOL = "pre_tool"
    PRE_LLM = "pre_llm"
    REGISTRATION = "registration"
    POST_TOOL = "post_tool"      # M3 — validate tool outputs
    POST_LLM = "post_llm"        # M3 — validate LLM responses
    # PRE_MESSAGE = "pre_message"  — deferred to M3 (requires Civitas MessageBus hook)
```

**Multi-stage rules**: a PolicyRule can apply to multiple stages by specifying a list: `stage: [pre_tool, pre_llm]`. The rule is evaluated at each listed stage. In YAML, this looks like:

```yaml
- name: enforce-grants
  stage: [pre_tool, pre_llm]    # same rule applies to both stages
  expression: "..."
  decision: deny
```

This avoids copy-pasting the same rule for each stage.

```python
class EnforcementMode(Enum):
    ADVISORY = "advisory"     # log only, never block
    SOFT = "soft"             # log + warn, don't block
    HARD = "hard"             # enforce — block on DENY

@dataclass(frozen=True)
class PolicyRule:
    """A single policy rule with a CEL expression."""
    name: str
    stage: EvaluationStage | list[EvaluationStage]  # single stage or list of stages
    expression: str                           # CEL expression
    decision: PolicyDecision                  # what to return if expression is true
    reason: str | None = None                 # human-readable explanation
    description: str | None = None
    priority: int = 0                         # higher = evaluated first
    enforcement: EnforcementMode = EnforcementMode.HARD
    approvers: list[str] = field(default_factory=list)  # for REQUIRE_APPROVAL
    enabled: bool = True

@dataclass
class PolicyResult:
    """Result of a policy evaluation."""
    decision: PolicyDecision
    policy_name: str | None = None    # None when no rule matched (all passed)
    reason: str | None = None
    approvers: list[str] | None = None
    enforcement: EnforcementMode = EnforcementMode.HARD
```

### EvaluationContext

```python
@dataclass
class ActionRequest:
    """What the agent is attempting to do."""
    resource: str                # "tool:database", "llm:claude-sonnet", "agent:writer"
    action: str                  # "read", "write", "invoke", "send"
    parameters: dict[str, Any] = field(default_factory=dict)

@dataclass
class EvaluationContext:
    """Full context passed to the policy engine for evaluation."""
    agent: AgentRecord           # identity, grants, trust, status, owner
    request: ActionRequest       # what is being attempted
    time: datetime               # current time (for time-based policies)
```

The CEL environment exposes:
- `agent.name`, `agent.agent_id`, `agent.owner`, `agent.status`
- `agent.trust.value` (float), `agent.trust.tier` (string)
- `agent.grants` (list of Grant objects with `.resources`, `.actions`, `.scope`, `.condition`)
- `request.resource`, `request.action`, `request.parameters`
- `time` (timestamp)

---

## PolicyEngine Protocol

```python
class PolicyEngine(Protocol):
    """Protocol for policy evaluation."""

    def load_policies(self, rules: list[PolicyRule]) -> None:
        """Load and compile policy rules. Raises on invalid CEL expressions."""
        ...

    async def evaluate(
        self, stage: EvaluationStage, context: EvaluationContext
    ) -> PolicyResult:
        """Evaluate all matching policies for the given stage and context."""
        ...
```

---

## CelPolicyEngine (Default Implementation)

```python
class CelPolicyEngine:
    """Default PolicyEngine using cel-python for in-process evaluation.
    
    Compile-once, evaluate-many: CEL expressions are compiled at load time.
    Evaluation is 1-3ms per expression in cel-python.
    
    Fail-closed: if a CEL expression errors during evaluation, the result
    is DENY. This is a non-configurable security invariant.
    """

    def load_policies(self, rules: list[PolicyRule]) -> None:
        # 1. Filter to enabled rules
        # 2. Group by stage
        # 3. Sort by priority (descending) within each stage
        # 4. Compile each CEL expression — fail immediately on compilation error
        # 5. Store compiled programs for fast evaluation
        ...

    async def evaluate(
        self, stage: EvaluationStage, context: EvaluationContext
    ) -> PolicyResult:
        # 1. Get compiled rules for this stage
        # 2. Build CEL activation from context (agent, request, time)
        # 3. Filter expired grants from agent.grants
        # 4. Evaluate grant conditions (grants with false conditions excluded)
        # 5. Evaluate each rule's expression in priority order
        # 6. First matching expression → return its PolicyResult
        # 7. If CEL evaluation errors → DENY (fail-closed), log error
        # 8. If no expression matches → ALLOW (all policies passed)
        ...
```

---

## Evaluation Stages

| Stage | When | PEP | Typical Policies |
|---|---|---|---|
| `pre_tool` | Before tool call | `GovernedToolProvider` | Grant checks, trust gates, tool ACLs |
| `pre_llm` | Before LLM call | `GovernedModelProvider` | Model allowlists, cost limits, grant checks |
| `pre_message` | Before agent-to-agent message | M3 (requires Civitas MessageBus hook) | Deferred — inter-agent communication governance |
| `registration` | When agent registers | `AgentRegistry` | Owner requirement, naming conventions |
| `post_tool` | After tool execution (M3) | `GovernedToolProvider` | Output PII detection, result size limits, sensitive data masking |
| `post_llm` | After LLM response (M3) | `GovernedModelProvider` | Schema compliance, content policy, response validation |

---

## Policy YAML Format

```yaml
presidium:
  policies:
    # Grant enforcement — the "default deny" for actions
    - name: enforce-grants
      stage: [pre_tool, pre_llm]
      expression: >
        !agent.grants.exists(g,
          request.resource in g.resources &&
          request.action in g.actions
        )
      decision: deny
      reason: "Agent does not hold a grant for this resource/action"
      priority: 100

    # Trust-gated write access
    - name: trust-gate-writes
      stage: pre_tool
      expression: >
        request.action == "write" && agent.trust.value < 0.7
      decision: require_approval
      reason: "Write actions require approval when trust is below 0.7"
      approvers: ["security-team@acme.com"]
      priority: 90

    # Model allowlist for production
    - name: production-model-allowlist
      stage: pre_llm
      expression: >
        !request.resource in ["llm:claude-sonnet", "llm:gpt-4o", "llm:gemini-pro"]
      decision: deny
      reason: "Model not in production allowlist"
      priority: 80

    # Owner required in service mode
    - name: require-owner
      stage: registration
      expression: "agent.owner == null || agent.owner == ''"
      decision: deny
      reason: "All agents must have an owner"
      priority: 100
      enforcement: soft  # warn but don't block during migration

    # New policy being tested (advisory mode)
    - name: restrict-expensive-models
      stage: pre_llm
      expression: >
        request.resource == "llm:claude-opus" && agent.trust.tier != "trusted"
      decision: deny
      reason: "Only trusted agents can use expensive models"
      priority: 70
      enforcement: advisory  # log only for 48 hours, then switch to hard
```

---

## Enforcement Modes

| Mode | Behavior | Use Case |
|---|---|---|
| `advisory` | Evaluate and log, never block | Testing new policies in production |
| `soft` | Evaluate, log, and warn (response includes warning) | Gradual rollout, migration period |
| `hard` | Evaluate and enforce — block on DENY | Production enforcement |

The recommended deployment pattern (from policy lifecycle research):
1. Deploy in `advisory` mode for 24-48 hours
2. Review logs for false positives
3. Switch to `soft` for 24-48 hours
4. Switch to `hard` when confident

**Enforcement mode and first-match-wins**: evaluation proceeds through rules in priority order. The first rule whose CEL expression evaluates to TRUE determines the result — both the decision AND the enforcement mode come from that rule. Rules whose expressions evaluate to FALSE are skipped (no match, continue to next).

Important: a rule with `enforcement: advisory` and `decision: deny` will MATCH and STOP evaluation (first-match-wins), but the denial is only logged, not enforced. Lower-priority rules are NOT reached. This means advisory rules can shadow hard rules if placed at higher priority.

**Recommended priority ordering:**

| Priority | Rule | Enforcement | Effect |
|---|---|---|---|
| 100 | enforce-grants | hard | Deny if no grant. Always first. |
| 90 | trust-gate-writes | hard | Require approval for low-trust writes. |
| 70 | new-cost-limit (testing) | advisory | Log but don't block expensive models. |

The grant enforcement rule at priority 100 ensures the security invariant is always checked first. Advisory rules for testing should have LOWER priority than critical enforcement rules.

---

## Fail-Closed Semantics

```python
async def evaluate(self, stage, context):
    for rule in self._rules_by_stage[stage]:
        try:
            result = rule.compiled_program.evaluate(activation)
            if result is True:
                return PolicyResult(
                    decision=rule.decision,
                    policy_name=rule.name,
                    reason=rule.reason,
                    approvers=rule.approvers,
                    enforcement=rule.enforcement,
                )
        except Exception as exc:
            # FAIL-CLOSED: evaluation error = DENY
            # This is non-configurable. If the policy can't evaluate,
            # the safe answer is DENY.
            logger.warning(
                "Policy '%s' evaluation error — fail-closed DENY: %s",
                rule.name, exc,
            )
            return PolicyResult(
                decision=PolicyDecision.DENY,
                policy_name=rule.name,
                reason=f"Policy evaluation error (fail-closed): {exc}",
                enforcement=EnforcementMode.HARD,  # errors always hard-enforce
            )

    # No rule matched → all policies passed → ALLOW
    return PolicyResult(
        decision=PolicyDecision.ALLOW,
        policy_name=None,
        reason="All policies passed",
    )
```

---

## Grant Integration

Grants and policies are separate concerns:
- **Grants** are data the agent holds (on `AgentRecord.grants`)
- **Policies** are rules that evaluate grants

The standard `enforce-grants` policy at priority 100 checks whether the agent holds a matching grant. This is a POLICY, not engine logic — users who want custom grant evaluation can replace it.

Grant conditions are evaluated during context preparation:
```python
# Before policy evaluation, filter grants:
# 1. Remove expired grants (expires_at < now)
# 2. Evaluate condition field on each remaining grant
#    - condition is a CEL expression evaluated against the context
#    - grant with false condition is excluded from agent.grants
# 3. The filtered grants list is what policies see
```

Example: grant `{resources: ["tool:database"], actions: ["write"], condition: "agent.trust.value >= 0.7"}` — when trust is 0.5, this grant is filtered out before policy evaluation. The `enforce-grants` policy sees no matching grant and returns DENY.

---

## Enforcement Point Integration

### GovernedModelProvider

```python
class GovernedModelProvider:
    """Wraps a Civitas ModelProvider with policy enforcement."""

    def __init__(self, provider: ModelProvider, engine: PolicyEngine, registry: AgentRegistry):
        self._provider = provider
        self._engine = engine
        self._registry = registry

    async def chat(self, model: str, messages: list, agent_name: str, **kwargs):
        record = await self._registry.lookup(agent_name)
        context = EvaluationContext(
            agent=record,
            request=ActionRequest(resource=f"llm:{model}", action="invoke"),
            time=datetime.now(UTC),
        )
        result = await self._engine.evaluate(EvaluationStage.PRE_LLM, context)

        if result.enforcement == EnforcementMode.ADVISORY:
            # Log but proceed
            await self._audit(result, context)
            return await self._provider.chat(model, messages, **kwargs)

        if result.decision == PolicyDecision.DENY:
            await self._audit(result, context)
            raise PolicyDeniedError(result.reason, result.policy_name)

        if result.decision == PolicyDecision.REQUIRE_APPROVAL:
            await self._audit(result, context)
            # Route to ApprovalService, await decision
            ...

        # ALLOW
        await self._audit(result, context)
        return await self._provider.chat(model, messages, **kwargs)
```

### GovernedToolProvider

Same pattern as GovernedModelProvider but evaluates `PRE_TOOL` stage and wraps `ToolProvider`.

---

## Civitas Integration Points

| Civitas Hook | Presidium Action |
|---|---|
| `ModelProvider` protocol | `GovernedModelProvider` wraps it, evaluates `pre_llm` policies |
| `ToolProvider` protocol | `GovernedToolProvider` wraps it, evaluates `pre_tool` policies |
| `AuditSink.emit()` | Every policy evaluation emits an audit event |
| `DynamicSupervisor.on_spawn_requested` | Evaluates `registration` stage policies |
| Topology YAML `presidium.policies` | Loaded and compiled at Runtime.start() |

---

## Design Decisions

| # | Decision | Choice | Alternatives Considered | Rationale |
|---|---|---|---|---|
| P1 | Policy language | CEL (cel-python, 1-3ms) | OPA Rego (3-10ms, requires sidecar), Cedar (no Python SDK), YAML glob matching (not expressive enough) | CEL: embeddable, non-Turing-complete, CNCF-aligned, type-safe at compile time. OPA/Cedar as contrib adapters for teams with existing policies. |
| P2 | Evaluation model | First-match-wins by priority, per-stage | All-rules evaluation, deny-overrides | Simple, deterministic, predictable. Operators control order via priority numbers. |
| P3 | Fail-closed | CEL errors → DENY (non-configurable) | Configurable fail-open, skip-on-error | Security invariant. Prevents exception-based policy bypass. From AGT research. |
| P4 | Enforcement modes | advisory/soft/hard per-policy | Global-only mode, no advisory | Per-policy modes enable gradual rollout. Advisory mode is essential for testing in production. From policy lifecycle pipeline pattern. |
| P5 | Default behavior | No match → ALLOW | No match → DENY | The engine is generic. Grant enforcement is a policy at priority 100, not engine logic. This lets users customize the "default deny" behavior without modifying the engine. |
| P6 | Grant integration | Grants are data, policies are logic | Grants as executable rules, grants as policies | Clean separation enables independent evolution. CEL reads grants as structured data. Don't conflate data with logic. |
| P7 | Evaluation stages | 3 stages for M2 (pre_tool, pre_llm, registration). post_tool, post_llm, and pre_message added in M3. | Single stage, 8 stages (AGT-style) | M2: 3 stages cover enforcement points. M3 adds post-execution validation (post_tool for output PII/filtering, post_llm for response compliance) and pre_message (requires Civitas MessageBus hook). Post-execution uses the same CEL engine — governance checks, not content validation (NeMo/Guardrails AI are separate concerns). |

---

## Open Questions (Deferred)

1. **Policy composition from agent groups**: should agents inherit policies from their team/group? (M3)
2. **Policy violations → trust score**: should policy violations automatically trigger trust decay? (M2 — lean yes, via TrustEvent.POLICY_VIOLATION)
3. **Post-execution evaluation**: M3 adds `post_tool` and `post_llm` stages for CEL-based output validation (PII detection, result filtering, schema compliance). Content validation (hallucination, toxicity) is a separate concern handled by NeMo Guardrails or Guardrails AI adapters in contrib.
4. **Custom CEL functions**: should we support custom function registration for domain-specific checks? (M2 — lean yes for extensibility)
5. **Policy versioning**: should policy rules have version numbers for audit trail? (M3)
