# The Full Stack

> How Civitas, Presidium, and external platforms fit together.

## Three Layers

| Layer | Concern | Projects |
|---|---|---|
| **Observe** | Watch agents, analyze behavior, alert, dashboard | Fiddler, Arize, Langfuse, Datadog |
| **Govern** | Control what agents can do, enforce policies, track identity | **Presidium** |
| **Run** | Keep agents alive, deliver messages, recover from crashes | **Civitas** |

Below these: agent frameworks (LangGraph, CrewAI, OpenAI Agents SDK) define how agents reason and act. Above them: enterprise systems (security, compliance, audit) consume governance signals.

## Why Three Layers, Not One?

Each layer has fundamentally different concerns:

**Runtime (Civitas)** cares about:
- Did the process crash? Restart it.
- Did the message arrive? Retry it.
- Is the transport alive? Reconnect it.
- Is the state persisted? Recover it.

**Governance (Presidium)** cares about:
- Is this agent authorized to do this? Check policy.
- Does this agent have the required trust level? Check registry.
- Is this LLM call within budget? Check gateway.
- Is this tool call safe? Check MCP gateway.

**Observability (External)** cares about:
- What happened? Show the trace.
- Is performance degrading? Alert.
- Is the agent hallucinating? Score it.
- Is compliance maintained? Report.

Combining all three into one project would create a 500K+ LOC monolith (see: Microsoft AGT). Separating them keeps each focused, testable, and replaceable.

## Integration Points

### Civitas → Presidium

Civitas provides extension points that Presidium hooks into:

| Civitas Extension | Presidium Usage |
|---|---|
| `Registry` | Extended with governance metadata (capabilities, trust, policies) |
| `Supervisor` | Policies become supervisor constraints |
| `MessageBus` | Action-level policy enforcement before delivery |
| `ModelProvider` protocol | LLM Gateway implements this |
| `ToolProvider` protocol | MCP Gateway implements this |
| `EvalLoop` | Extended with governance metrics |
| `ExportBackend` protocol | Fiddler/Arize/Langfuse exporters |
| OTEL spans | Enriched with governance context (policy decisions, trust scores) |

### Presidium → External Platforms

Presidium generates telemetry that external platforms consume:

| Signal | Format | Consumers |
|---|---|---|
| OTEL traces with governance spans | OpenTelemetry | Fiddler, Datadog, Jaeger |
| Eval scores | ExportBackend protocol | Fiddler, Arize, Langfuse |
| Policy decision logs | Structured JSON | SIEM, audit systems |
| Trust score history | Time-series | Prometheus, Grafana |
| Cost tracking | Metrics | FinOps tools, dashboards |

## Deployment Scenarios

### Scenario 1: Developer Laptop

```
Single process, InProcessTransport
Civitas + Presidium as Python libraries
Console output for observability
```

### Scenario 2: Team Staging

```
Multi-process, ZMQTransport
Civitas + Presidium with OTEL export
Fiddler or Langfuse for dashboards
```

### Scenario 3: Production

```
Distributed, NATSTransport
Civitas + Presidium across containers
Full OTEL pipeline → Fiddler + Datadog
Policy engine with OPA/Cedar
SOC 2 audit trail
```

Same code, different topology config. That's the Civitas scaling ladder, extended with Presidium governance at every level.
