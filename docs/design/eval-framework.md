# Design: Audit Framework

> `presidium-audit` — Governance metrics, compliance reporting, and external platform integration.

**Status:** Draft
**Package:** `presidium-audit` _(formerly `presidium-eval` — renamed to distinguish from Civitas's `EvalLoop`, which handles agent self-correction signals; this package is about external accountability, not internal quality)_
**Milestone:** M4

## Problem Statement

Existing observability tools (Fiddler, Arize, Langfuse) evaluate agent outputs for quality, safety, and performance. They don't evaluate governance compliance: Is the agent staying within policy? Is its trust score trending correctly? Is it using only authorized tools? Presidium needs an audit layer that generates governance metrics and delivers them to external platforms.

This is distinct from Civitas's `EvalLoop`, which produces self-correction signals that flow back into the agent's reasoning loop. Audit metrics flow outward to compliance stakeholders, not inward to the agent.

## Goals

1. Define governance-specific metrics (compliance rate, denial counts, trust drift, budget utilization)
2. Aggregate governance signals from the `AuditSink` event pipeline and policy engine
3. Export to external platforms (Fiddler, Arize, Langfuse, Prometheus, custom backends)
4. Feed compliance metrics back into trust scores (closed feedback loop via `AgentRegistry.update_trust()`)
5. Generate structured compliance reports (EU AI Act, NIST AI RMF, SOC 2 mapping)

## Non-Goals

- Replace Fiddler/Arize — Presidium generates governance metrics, they dashboard them
- LLM output quality scoring — that's the external platform's job
- Real-time guardrails / content safety — that's `presidium-policy` (enforcement) and Fiddler/NeMo Guardrails
- Issuing compliance certificates — human audit process owns that
- Replacing Civitas's `EvalLoop` — these run in parallel, not as substitutes

## Design

### Governance Metrics

```python
@dataclass
class GovernanceMetrics:
    """Metrics computed per agent per evaluation window."""
    agent_name: str
    window_start: datetime
    window_end: datetime
    policy_compliance_rate: float       # % of actions that passed policy
    denial_count: int                   # Number of denied actions
    denial_breakdown: dict[str, int]    # By policy rule name
    approval_pending_count: int         # Actions waiting for human approval
    approval_resolution_time_p50_s: float  # Median time-to-decision for approvals
    trust_score_delta: float            # Change in trust score this window
    tool_usage_authorized: float        # % of tool calls to authorized tools
    llm_budget_utilization: float       # % of LLM budget consumed
    restart_count: int                  # Number of supervisor restarts
    escalation_count: int               # Number of supervisor escalations
    mean_policy_eval_latency_ms: float  # Average policy evaluation latency
```

### Export Backends

```python
class GovernanceExporter(Protocol):
    """Exports governance metrics to external platforms."""

    async def export(
        self,
        agent_name: str,
        metrics: GovernanceMetrics,
    ) -> None: ...

# Implementations:
class FiddlerExporter(GovernanceExporter): ...
class ArizeExporter(GovernanceExporter): ...
class LangfuseExporter(GovernanceExporter): ...
class PrometheusExporter(GovernanceExporter): ...
class ConsoleExporter(GovernanceExporter): ...
```

### Civitas Integration: AuditSink

`presidium-audit` subscribes to Civitas's `AuditSink` event pipeline (integration point 4). Civitas emits structured audit events for every significant action; `presidium-audit` enriches those events with governance context (policy decision, agent grants, trust score at time of event) before aggregating and exporting.

```python
class GovernanceAuditSink:
    """Subscribes to Civitas AuditSink; enriches and aggregates governance events."""

    async def on_event(self, event: AuditEvent) -> None:
        record = await self._registry.lookup(event.agent_name)
        enriched = GovernanceEvent(
            **event.__dict__,
            policy_decision=await self._policy.get_last_decision(event.agent_name),
            trust_score=record.trust_score if record else None,
            grants=record.grants if record else [],
        )
        await self._aggregator.ingest(enriched)
```

### EvalLoop Attachment

`presidium-audit` attaches governance metrics alongside Civitas's self-correction signals (integration point 6). These run as parallel streams — governance metrics do not replace self-correction signals:

```python
class GovernanceEvalAttachment:
    """Attaches governance metrics to Civitas EvalLoop without replacing it."""

    async def on_eval_tick(self, agent_name: str) -> None:
        metrics = await self._aggregator.compute(agent_name)

        for exporter in self._exporters:
            await exporter.export(agent_name, metrics)

        # Feed compliance signals back into trust
        if metrics.policy_compliance_rate < 0.95:
            await self._registry.update_trust(
                agent_name, -0.01, "compliance below 95% threshold"
            )
        elif metrics.denial_count == 0 and metrics.policy_compliance_rate == 1.0:
            await self._registry.update_trust(
                agent_name, +0.005, "perfect compliance window"
            )
```

### Feedback Loop

![Audit Feedback Loop](../../assets/audit-feedback-loop.svg)

## Open Questions

- What's the default evaluation window? (30s? 1m? 5m?) Proposal: configurable, default 1m.
- Should trust adjustments trigger automatically, or just be reported for human confirmation?
- How do we handle audit for agents that run infrequently (sparse windows)?
- What Fiddler API endpoints does the exporter target? Need to consult Fiddler docs.
- Compliance report format: structured JSON for machine consumption vs. rendered PDF for auditors?
