# RFC-001: Presidium Scope and Boundaries

**Status:** Draft
**Author:** Jeryn Mathew
**Created:** 2026-04-30

## Summary

This RFC defines what Presidium is, what it isn't, and the boundaries between Presidium, Civitas, and external platforms.

## Motivation

Presidium could become many things: a framework, a platform, an observability tool, a compliance engine. Without explicit scope boundaries, feature creep will dilute the project's value proposition and make it unshippable.

## Scope: What Presidium IS

Presidium is a **governance layer for AI agent systems**, built on Civitas. It provides:

1. **Agent Registry** — identity, capabilities, trust tracking
2. **Policy Engine** — declarative policies enforced as runtime constraints
3. **LLM Gateway** — governed LLM access (routing, rate limiting, cost tracking)
4. **MCP Gateway** — governed tool access (ACLs, poisoning detection)
5. **Eval Framework** — governance-specific metrics with external platform export

### Design Principles

- Governance is architectural (supervisor constraints, not sidecars)
- Python-first (no multi-language until Python is excellent)
- Developer-centric (simple things simple, complex things possible)
- Vendor-neutral (no cloud lock-in, OTEL for telemetry)
- CNCF-aligned (prefer CNCF standards where applicable — SPIFFE for identity, OTEL for observability, CEL for policy — to enable enterprise adoption and interoperability with existing infrastructure)
- Open source (Apache 2.0, free forever for core)

## Out of Scope: What Presidium is NOT

| NOT This | That's This | Why |
|---|---|---|
| Agent framework | LangGraph, CrewAI, OpenAI Agents SDK | Presidium governs agents, doesn't define how they reason |
| Agent runtime | Civitas | Presidium depends on Civitas, doesn't replace it |
| Observability platform | Fiddler, Arize, Langfuse | Presidium generates telemetry, doesn't dashboard it |
| Content safety | Fiddler Guardrails, NeMo Guardrails | Presidium governs capabilities, not content quality |
| LLM provider | Anthropic, OpenAI, Google | Presidium routes to providers, doesn't serve models |
| Compliance platform | AGT Agent Compliance | Presidium generates compliance signals, doesn't certify |
| Web dashboard | Future project | Presidium is a library/runtime, not a UI |

## Boundary Rules

### Civitas Boundary

Civitas owns:
- Supervision trees, restart strategies, escalation
- Message passing, mailboxes, backpressure
- Transport abstraction (InProcess, ZMQ, NATS)
- State persistence (StateStore)
- OTEL tracing
- LLM provider plugins (AnthropicProvider, etc.)
- MCP client integration
- HTTP Gateway infrastructure

Presidium extends (does not duplicate):
- Registry → adds governance metadata
- Supervisor → adds policy constraints
- MessageBus → adds action-level enforcement
- ModelProvider → wraps with rate limiting and cost tracking
- ToolProvider → wraps with access control
- EvalLoop → adds governance metrics
- ExportBackend → adds platform exporters

### External Platform Boundary

Presidium generates signals. External platforms consume them.

| Signal | Presidium Generates | External Consumes |
|---|---|---|
| OTEL spans (governance-enriched) | ✅ | Fiddler, Datadog, Jaeger |
| Eval metrics (governance) | ✅ | Fiddler, Arize, Langfuse |
| Policy decision logs | ✅ | SIEM, audit systems |
| Trust score history | ✅ | Prometheus, Grafana |

Presidium does NOT:
- Build dashboards (that's the external platform's job)
- Score content quality (that's Fiddler Trust Models)
- Generate compliance certificates (that's AGT or manual audit)

## Decision

Accept this RFC as the governing scope document for Presidium. All package proposals must demonstrate alignment with this scope. Features that cross boundaries should be proposed as separate RFCs with clear justification.

## Open Questions

- Should Presidium include a minimal TUI dashboard for local development? (Not a web UI, just a terminal interface for debugging.)
- At what point does Presidium need its own CLI vs. extending Civitas's CLI?
- Should `presidium-sdk` re-export Civitas APIs or keep them separate imports?
