# Design: Eval Framework

> `presidium-eval` — Governance-aware evaluation and external platform integration.

**Status:** Draft
**Package:** `presidium-eval`
**Milestone:** M4

## Problem Statement

Existing eval tools (Fiddler, Arize, Langfuse) evaluate agent outputs for quality, safety, and performance. They don't evaluate governance compliance: Is the agent staying within policy? Is its trust score trending correctly? Is it using authorized tools? Presidium needs an eval layer that bridges governance metrics to external platforms.

## Goals

1. Define governance-specific evaluation metrics
2. Score agent behavior against governance criteria
3. Export to external platforms (Fiddler, Arize, Langfuse, custom)
4. Feed evaluation results back into trust scores (closed loop)
5. Extend Civitas's EvalLoop with governance context

## Non-Goals

- Replace Fiddler/Arize — Presidium generates governance metrics, they dashboard them
- LLM output quality scoring — that's the external platform's job
- Real-time guardrails — that's `presidium-policy` (enforcement) and Fiddler (content safety)

## Design

### Governance Metrics

```python
@dataclass
class GovernanceMetrics:
    """Metrics computed per agent per evaluation window."""
    policy_compliance_rate: float       # % of actions that passed policy
    denial_count: int                   # Number of denied actions
    approval_pending_count: int         # Actions waiting for approval
    trust_score_delta: float            # Change in trust score this window
    tool_usage_authorized: float        # % of tool calls to authorized tools
    llm_budget_utilization: float       # % of LLM budget consumed
    restart_count: int                  # Number of supervisor restarts
    mean_action_latency_ms: float       # Average policy evaluation latency
```

### Export Backends

```python
class GovernanceExporter(Protocol):
    """Exports governance metrics to external platforms."""

    async def export(
        self,
        agent_name: str,
        metrics: GovernanceMetrics,
        window: TimeWindow,
    ) -> None: ...

# Implementations:
class FiddlerExporter(GovernanceExporter): ...
class ArizeExporter(GovernanceExporter): ...
class LangfuseExporter(GovernanceExporter): ...
class PrometheusExporter(GovernanceExporter): ...
class ConsoleExporter(GovernanceExporter): ...
```

### Feedback Loop

Eval results feed back into the registry:

```
Agent acts → Policy evaluates → OTEL span emitted
                                      │
                                      ▼
                              Eval loop collects
                                      │
                                      ▼
                              Governance metrics computed
                                      │
                            ┌─────────┼─────────┐
                            ▼         ▼         ▼
                       Trust score   Export    Alert
                       adjustment   (Fiddler)  (if threshold)
```

### Civitas Integration

```python
class GovernanceEvalLoop(EvalLoop):
    """Extends Civitas EvalLoop with governance metrics."""

    async def evaluate(self, agent_name: str) -> GovernanceMetrics:
        # Collect policy decisions from the last window
        decisions = await self.policy_engine.get_decisions(agent_name, self.window)

        # Compute metrics
        metrics = GovernanceMetrics(
            policy_compliance_rate=sum(d.decision == ALLOW for d in decisions) / len(decisions),
            denial_count=sum(d.decision == DENY for d in decisions),
            # ... etc
        )

        # Export to all backends
        for exporter in self.exporters:
            await exporter.export(agent_name, metrics, self.window)

        # Feed back into trust
        if metrics.policy_compliance_rate < 0.95:
            await self.registry.update_trust(
                agent_name, -0.01, "compliance below 95%"
            )

        return metrics
```

## Open Questions

- What's the default evaluation window? (30s? 1m? 5m?)
- Should eval trigger trust changes automatically, or just report?
- How do we handle eval for agents that run infrequently?
- What Fiddler API endpoints does the exporter target?
