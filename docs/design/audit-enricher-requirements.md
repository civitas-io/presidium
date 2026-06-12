# Audit Enricher: Requirements

> What the AuditEnricher must do — governance context enrichment for Civitas audit events.
> Status: Draft
> Milestone: M2 (Core Interfaces + CEL Policy)

## Overview

Civitas emits structured audit events (`AuditEvent`) at 5 chokepoints: message routing, secret access, tool calls, sandbox execution, and sandbox denials. These events contain operational data (who, what, when) but no governance context (was this authorized? what grant permitted it? what was the agent's trust level?).

The AuditEnricher is a middleware `AuditSink` that wraps a downstream sink (JsonlFileSink, OtlpSink, etc.), enriches each event with governance data from the AgentRegistry and PolicyEngine, and forwards the enriched event. No Civitas code changes required — Presidium injects the enricher as the sink, and the enricher delegates to the original sink.

Additionally, Presidium components (PolicyEngine, CredentialProvider, ApprovalService, AgentRegistry) emit their own governance-specific audit events. The AuditEnricher provides a unified pipeline for both Civitas operational events and Presidium governance events.

---

## Functional Requirements

### FR-1: Middleware Pattern

**FR-1.1**: The AuditEnricher MUST implement the Civitas `AuditSink` protocol (emit, flush, close).
**FR-1.2**: The AuditEnricher MUST wrap a downstream `AuditSink` (the original sink from topology YAML).
**FR-1.3**: The AuditEnricher MUST forward every event to the downstream sink after enrichment.
**FR-1.4**: If enrichment fails (registry lookup error, etc.), the original unenriched event MUST still be forwarded — enrichment failures MUST NOT drop audit events.
**FR-1.5**: Events that already contain a `governance` key in their `details` dict MUST be forwarded without enrichment (idempotency guard). This prevents re-enrichment of events emitted by Presidium components that include their own governance context.

### FR-2: Governance Context Enrichment

**FR-2.1**: For events with a non-empty `agent` field, the AuditEnricher MUST look up the agent's record from the AgentRegistry and add:
  - `governance.agent_id`: the agent's `presidium://` identity URI
  - `governance.trust_value`: current trust score (float)
  - `governance.trust_tier`: current trust tier (string)
  - `governance.owner`: agent's owner (string or null)
**FR-2.2**: The enrichment data MUST be added to the event's `details` dict under a `governance` key (namespaced to avoid collisions with Civitas's existing detail fields).
**FR-2.3**: Events with an empty `agent` field (system events) MUST be forwarded unenriched.
**FR-2.4**: Registry lookups MUST be cached with a short TTL (default 5 seconds) to avoid per-event database queries on high-throughput message buses.

### FR-2.5: AuditEvent Type Contract

**FR-2.5**: All Presidium components MUST use Civitas's `AuditEvent` TypedDict (from `civitas.audit.types`) — not a custom dataclass. Construction uses keyword arguments; access uses dict-style (`event["agent"]`, `event.get("details", {})`). This ensures compatibility with all Civitas `AuditSink` implementations.

### FR-3: Presidium Event Types

**FR-3.1**: The AuditEnricher MUST support emitting Presidium-specific governance events alongside Civitas operational events:
  - `policy.evaluated` — every policy evaluation (stage, decision, policy_name, resource, action, evaluation_ms)
  - `credential.access` — every credential resolution (credential_name, result, grant_match, backend)
  - `approval.requested` — every approval request created (request_id, resource, action, approvers)
  - `approval.decided` — every approval decision (request_id, decision, decided_by, wait_time_seconds)
  - `agent.registered` / `agent.deregistered` — registry lifecycle events
  - `status.changed` — agent lifecycle state transitions (REGISTERED → RUNNING, RUNNING → STOPPED, etc.)
  - `trust.updated` — trust score changes (old_value, new_value, trigger_event, tier_change)
  - `grant.added` / `grant.removed` — grant mutations
**FR-3.2**: All Presidium events MUST follow the same `AuditEvent` TypedDict shape as Civitas events (event, ts, agent, signer_id, details).

### FR-4: Audit

**FR-4.1**: The enrichment pipeline itself MUST NOT be audited (no infinite loops — the enricher does not emit events about its own enrichment).
**FR-4.2**: Enrichment failures MUST be logged via Python's `logging` module, not via the audit pipeline.

### FR-5: Protocol and Extensibility

**FR-5.1**: `AuditEnricher` MUST be a Protocol — enrichment logic is swappable.
**FR-5.2**: `InProcessAuditEnricher` MUST be the default implementation in the `presidium` core package.
**FR-5.3**: The enricher MUST work with any Civitas `AuditSink` as its downstream (JsonlFileSink, OtlpSink, SyslogSink, NullSink, custom sinks).

---

## Non-Functional Requirements

### NFR-1: Performance
- Enrichment MUST add < 1ms overhead per event (registry lookup cached, no I/O per event)
- The enricher MUST NOT block Civitas's event loop — enrichment is async
- Cache TTL MUST be configurable (default 5 seconds)

### NFR-2: Reliability
- Enrichment failure MUST NOT drop the original event — fail-open for forwarding
- Downstream sink failures are the downstream's responsibility, not the enricher's

### NFR-3: Ordering
- Events MUST be forwarded in the order received (no reordering during enrichment)

---

## Design Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| E1 | Middleware pattern | AuditEnricher wraps downstream AuditSink | No Civitas code changes. Same pattern as GovernedModelProvider wrapping ModelProvider. |
| E2 | Fail-open forwarding | Enrichment errors don't drop events | Audit completeness is more important than enrichment completeness. A raw event is better than no event. |
| E3 | Namespaced enrichment | Governance data under `details.governance` key | Avoids collisions with Civitas's existing detail fields (sender, recipient, etc.). |
| E4 | Cached registry lookups | 5-second TTL cache for agent records | High-throughput message buses emit thousands of events/second. Per-event DB queries would be a bottleneck. |
| E5 | Unified event pipeline | Both Civitas and Presidium events flow through the same sink | One audit stream, one log file, one OTEL exporter. Simplifies ops and compliance. |

---

## Out of Scope (M2)

- External platform-specific exporters (Datadog, Splunk enrichment adapters) — M3
- Compliance report generation from audit events — M3+
- Tamper-evident audit chains (hash linking, Merkle proofs) — M3+
- Audit event filtering/sampling for high-volume deployments — M3
- Real-time audit alerting (fire webhook on specific event patterns) — M3
