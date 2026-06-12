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
