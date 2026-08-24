# Getting Started

> Add governance to a Civitas agent system in under 5 minutes.

## Install

```bash
pip install presidium
```

## Programmatic Usage

The fastest way to add governance — build components in Python code:

```python
import asyncio
from presidium import (
    AgentRecord, Grant, PolicyRule, PolicyDecision,
    EvaluationStage, CelPolicyEngine, InMemoryRegistry,
    GovernedRuntime,
)

async def main():
    # 1. Create a registry and register an agent with grants
    registry = InMemoryRegistry()
    await registry.register(AgentRecord(
        agent_id="presidium://local/researcher",
        name="researcher",
        public_key="",
        owner="alice@acme.com",
        grants=[
            Grant(resources=["tool:web_search"], actions=["invoke"]),
            Grant(resources=["tool:database"], actions=["read"]),
            Grant(resources=["llm:claude-sonnet"], actions=["invoke"]),
        ],
    ))

    # 2. Define policies
    #
    # Presidium denies by default: if no policy rule matches a request, the
    # request is denied (docs/design/policy-engine.md's "Design Decisions"
    # P5) -- so a real policy set needs an explicit terminal ALLOW rule for
    # "nothing else objected," not just DENY rules. This is deliberate:
    # forgetting a DENY rule for something new should fail safe (denied),
    # not silently permit it.
    engine = CelPolicyEngine()
    engine.load_policies([
        PolicyRule(
            name="enforce-grants",
            stage=[EvaluationStage.PRE_TOOL, EvaluationStage.PRE_LLM],
            expression="""
                !agent.grants.exists(g,
                    request.resource in g.resources &&
                    request.action in g.actions
                )
            """,
            decision=PolicyDecision.DENY,
            reason="No matching grant for this resource/action",
            priority=100,
        ),
        PolicyRule(
            name="allow-granted-actions",
            stage=[EvaluationStage.PRE_TOOL, EvaluationStage.PRE_LLM],
            expression="true",
            decision=PolicyDecision.ALLOW,
            reason="Cleared enforce-grants -- agent holds a matching grant",
            priority=0,
        ),
    ])

    # 3. Build the governed runtime
    rt = GovernedRuntime(registry=registry, engine=engine)

    # 4. Check tool access
    result = await rt.tool_provider.check("researcher", "web_search")
    print(f"web_search: {result.decision.value}")  # allow

    result = await rt.tool_provider.check("researcher", "database", "read")
    print(f"database read: {result.decision.value}")  # allow

    try:
        await rt.tool_provider.check("researcher", "database", "write")
    except Exception as e:
        print(f"database write: denied — {e}")  # denied, no write grant

asyncio.run(main())
```

## YAML Configuration

For Civitas topology files, add a `presidium:` block:

```yaml
# topology.yaml
transport:
  type: in_process

supervision:
  name: root
  children:
    - agent:
        name: researcher
        type: myapp.ResearchAgent

presidium:
  registry:
    trust_domain: acme.com

  # Presidium denies by default when no rule matches (real, deliberate --
  # see docs/design/policy-engine.md P5) -- add an explicit terminal ALLOW
  # rule for "nothing else objected," don't rely on an implicit allow.
  policies:
    - name: enforce-grants
      stage: [pre_tool, pre_llm]
      expression: >
        !agent.grants.exists(g,
          request.resource in g.resources &&
          request.action in g.actions
        )
      decision: deny
      reason: "No matching grant"
      priority: 100

    - name: allow-granted-actions
      stage: [pre_tool, pre_llm]
      expression: "true"
      decision: allow
      reason: "Cleared enforce-grants -- agent holds a matching grant"
      priority: 0

    - name: trust-gate-writes
      stage: pre_tool
      expression: >
        request.action == "write" && agent.trust.value < 0.7
      decision: require_approval
      reason: "Write actions need approval when trust < 0.7"
      approvers: ["security@acme.com"]
      priority: 90

  agents:
    researcher:
      owner: alice@acme.com
      grants:
        - resources: ["tool:web_search"]
          actions: ["invoke"]
        - resources: ["tool:database"]
          actions: ["read"]
        - resources: ["llm:claude-sonnet"]
          actions: ["invoke"]
```

Load and run:

```python
from presidium import GovernedRuntime

rt = GovernedRuntime.from_config("topology.yaml")
await rt.start()
```

## Key Concepts

| Concept | What it does |
|---|---|
| **AgentRecord** | Identity + grants + trust score for each agent |
| **Grant** | Structured permission: resources × actions × scope × CEL condition |
| **PolicyRule** | CEL expression evaluated at governance checkpoints |
| **PolicyDecision** | ALLOW, DENY, or REQUIRE_APPROVAL |
| **TrustScorer** | 0.0-1.0 trust with decay and 3 tiers (Trusted/Standard/Restricted) |
| **GovernedRuntime** | Wires everything together, wraps Civitas Runtime |

## Default-deny -- read this before writing your own policies

**If no policy rule matches a request, Presidium denies it.** This is a real, deliberate design
choice (see [Policy Engine design](../design/policy-engine.md)'s "Design Decisions" P5) -- not a
bug, and not the old behavior (Presidium used to default to ALLOW when nothing matched; that
changed 2026-08-24). Concretely: every real policy set needs an explicit terminal ALLOW rule
(like `allow-granted-actions` above, `priority: 0` so it only fires after every real DENY/
REQUIRE_APPROVAL rule has had a chance to fire first) for the "nothing else objected" case --
otherwise every request to a stage with policies attached will be denied.

Two real, explicit escape hatches exist if you need something else, both on `CelPolicyEngine`'s
constructor:

- `allow_unmatched_requests=True` -- restores the old always-ALLOW-on-no-match behavior outright.
- `unmatched_enforcement=EnforcementMode.ADVISORY` -- keeps the DENY *decision* (so it shows up in
  your real audit logs) while running in advisory mode (logged, not blocking) -- a real, gentle
  migration path if you're not sure your policies are ready for hard enforcement yet.

## Enforcement Modes

Policies support gradual rollout:

| Mode | Behavior |
|---|---|
| `hard` (default) | Block on DENY |
| `soft` | Log + warn, don't block |
| `advisory` | Log only |

Deploy new policies in `advisory` for 24-48h, then `soft`, then `hard`.

## Next Steps

- [Agent Registry design](../design/agent-registry.md) — SPIFFE identity, grants, trust scoring
- [Policy Engine design](../design/policy-engine.md) — CEL expressions, evaluation stages, fail-closed semantics
- [Topology Integration](../design/topology-integration.md) — full YAML format reference
