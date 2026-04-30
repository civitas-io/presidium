# Design: Policy Engine

> `presidium-policy` — Declarative policy definition, evaluation, and enforcement.

**Status:** Draft
**Package:** `presidium-policy`
**Milestone:** M2

## Problem Statement

Agent systems lack deterministic policy enforcement. Agents can call any tool, access any data, invoke any LLM — with no constraints beyond what the framework allows. Guardrails (Fiddler, NeMo) address content safety (hallucination, toxicity) but not structural governance: "Can this agent perform this action at all?"

## Goals

1. Declarative policy definitions (YAML primary, OPA/Cedar future)
2. Sub-millisecond policy evaluation (must not add perceptible latency)
3. Three decision types: ALLOW, DENY, REQUIRE_APPROVAL
4. Policies enforced as Civitas supervisor constraints (not a separate layer)
5. Action-level granularity (per tool call, per LLM request, per message)

## Non-Goals

- Content safety (hallucination, toxicity detection) — that's Fiddler's job
- LLM output filtering — that's guardrails, not policy
- Real-time policy editing in production (M2 = static policies loaded at startup)

## Design

### Policy Definition (YAML)

```yaml
policies:
  - name: analyst-readonly
    description: "Analysts can read data but cannot write or delete"
    agents:
      - "analyst-*"        # Glob matching
    rules:
      - action: "read_*"
        decision: allow
      - action: "write_*"
        decision: deny
        reason: "Analysts are read-only"
      - action: "delete_*"
        decision: deny
        reason: "Analysts cannot delete data"

  - name: rate-limited-all
    description: "All agents limited to 100 LLM calls per minute"
    agents:
      - "*"
    rules:
      - action: "llm_call"
        decision: allow
        constraints:
          rate_limit:
            requests: 100
            window: "1m"

  - name: approval-required-production
    description: "Production writes require human approval"
    agents:
      - "writer-*"
    rules:
      - action: "write_production_*"
        decision: require_approval
        approval:
          min_approvals: 1
          timeout_minutes: 30
```

### Policy Engine Protocol

```python
class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"

@dataclass
class PolicyResult:
    decision: PolicyDecision
    policy_name: str
    rule_index: int
    reason: str | None = None

class PolicyEngine(Protocol):
    async def evaluate(
        self,
        agent: str,
        action: str,
        context: dict[str, Any],
    ) -> PolicyResult: ...

    def load_policies(self, path: Path) -> None: ...
    def get_policies_for_agent(self, agent: str) -> list[Policy]: ...
```

### Evaluation Order

1. Find all policies matching the agent name (glob matching)
2. Within each policy, evaluate rules top-to-bottom (first match wins)
3. If multiple policies match, most restrictive decision wins (DENY > REQUIRE_APPROVAL > ALLOW)
4. If no rule matches, default to DENY (secure by default)

### Supervisor Integration

Policies become supervisor constraints:

```python
# Instead of this (Civitas alone):
supervisor = Supervisor(
    children=[analyst_agent],
    strategy=RestartStrategy.ONE_FOR_ONE,
)

# Presidium adds governance:
supervisor = GovernedSupervisor(
    children=[analyst_agent],
    strategy=RestartStrategy.ONE_FOR_ONE,
    policies=["analyst-readonly", "rate-limited-all"],
    # Policy violations trigger ErrorAction.STOP, not just logging
)
```

## Alternatives Considered

1. **OPA Rego from the start** — Too complex for M2. YAML is readable and sufficient. OPA planned for M3+.
2. **Cedar (AWS)** — Same reasoning. Good policy language, but YAML first.
3. **Content-based policies** — Out of scope. Content safety is observability (Fiddler), not structural governance.
4. **Permissive default (ALLOW if no match)** — Security anti-pattern. Default DENY is industry standard.

## Open Questions

- How do policies compose? Can an agent inherit policies from its group/team?
- Should policy violations affect trust scores automatically?
- What's the approval workflow for REQUIRE_APPROVAL? Queue? Webhook? Slack?
- How do policies interact with Civitas's topology YAML format?
