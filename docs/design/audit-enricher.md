# Design: Audit Enricher

> Governance context enrichment for Civitas audit events.

**Status:** Draft (June 2026)
**Package:** `presidium` (protocol + InProcessAuditEnricher)
**Milestone:** M2
**Requirements:** [audit-enricher-requirements.md](audit-enricher-requirements.md)

## Problem Statement

Civitas emits audit events at operational chokepoints (message routing, secret access, tool calls, sandbox operations). These events answer "what happened?" but not "was it authorized? what governance rules applied? what was the agent's trust level?" Compliance (EU AI Act Art. 12, ISO 42001 Annex A.8) requires audit trails that link actions to authorization decisions.

## Goals

1. Enrich Civitas audit events with governance context (trust, grants, identity)
2. Provide a unified pipeline for both Civitas operational events and Presidium governance events
3. No changes to Civitas core — middleware pattern via AuditSink protocol
4. Fail-open: enrichment errors never drop audit events

## Non-Goals (M2)

- Platform-specific export adapters (Datadog, Splunk enrichment) — M3
- Tamper-evident audit chains — M3+
- Compliance report generation — M3+

---

## Architecture

```
Civitas components emit AuditEvent
    ↓
    ↓  message.route, secret.access, tool.call, ...
    ↓
AuditEnricher (Presidium middleware)
    ↓  1. Look up agent in AgentRegistry (cached)
    ↓  2. Add governance context to details.governance
    ↓  3. Forward enriched event
    ↓
Downstream AuditSink (Civitas)
    ↓  JsonlFileSink / OtlpSink / SyslogSink
    ↓
Storage / External Platform

Presidium components also emit directly:
    PolicyEngine  →  policy.evaluated
    CredentialProvider  →  credential.access
    ApprovalService  →  approval.requested, approval.decided
    AgentRegistry  →  agent.registered, trust.updated, grant.added
    ↓
    ↓  (same AuditEnricher pipeline)
    ↓
Downstream AuditSink
```

---

## Data Model

### AuditEnricher Protocol

```python
from __future__ import annotations
from typing import Protocol
from civitas.audit.types import AuditEvent, AuditSink

class AuditEnricher(Protocol):
    """Protocol for governance-enriched audit event processing.
    
    Wraps a downstream AuditSink, enriches events with governance
    context, and forwards them.
    """
    
    async def emit(self, event: AuditEvent) -> None:
        """Enrich and forward an audit event."""
        ...
    
    async def flush(self) -> None:
        """Flush the downstream sink."""
        ...
    
    async def close(self) -> None:
        """Close the downstream sink."""
        ...
```

Note: `AuditEnricher` IS an `AuditSink` (same interface). It's a structural subtype — any `AuditEnricher` can be used wherever an `AuditSink` is expected. The separate Protocol exists for documentation clarity, not type distinction.

### AuditEvent Type

Civitas's `AuditEvent` is a `TypedDict` (not a dataclass). This means:
- **Construction**: `AuditEvent(event="...", ts="...", agent="...", signer_id="...", details={...})`
- **Access**: dict-style — `event["agent"]`, `event.get("details", {})`, `event["details"]["governance"]`
- **Mutation**: create a new dict rather than mutating (TypedDicts are structurally dicts)

All Presidium components MUST use this type consistently. Import from `civitas.audit.types`.

### Enrichment Shape

Governance data is added under `details.governance` to avoid collisions with Civitas's existing detail fields:

```python
# Original Civitas event
AuditEvent(
    event="message.route",
    ts="2026-06-11T10:00:00Z",
    agent="researcher",
    signer_id="researcher",
    details={
        "sender": "researcher",
        "recipient": "database_tool",
        "type": "tool_call",
        "message_id": "msg-uuid-123",
    }
)

# After enrichment
AuditEvent(
    event="message.route",
    ts="2026-06-11T10:00:00Z",
    agent="researcher",
    signer_id="researcher",
    details={
        "sender": "researcher",
        "recipient": "database_tool",
        "type": "tool_call",
        "message_id": "msg-uuid-123",
        "governance": {                          # added by AuditEnricher
            "agent_id": "presidium://acme.com/prod/researcher",
            "trust_value": 0.72,
            "trust_tier": "trusted",
            "owner": "alice@acme.com",
        },
    }
)
```

---

## Default Implementation: InProcessAuditEnricher

```python
class InProcessAuditEnricher:
    """Default AuditEnricher. Enriches events with governance context in-process.
    
    Registry lookups are cached with a configurable TTL to avoid
    per-event I/O on high-throughput buses.
    """
    
    def __init__(
        self,
        downstream: AuditSink,
        registry: AgentRegistry,
        cache_ttl: float = 5.0,
    ):
        self._downstream = downstream
        self._registry = registry
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[dict, float]] = {}  # agent_name -> (governance_data, timestamp)
    
    async def emit(self, event: AuditEvent) -> None:
        agent_name = event.get("agent", "")
        
        # Guard: don't re-enrich events that already have governance context
        if "governance" in event.get("details", {}):
            await self._downstream.emit(event)
            return
        
        if agent_name:
            try:
                governance = await self._get_governance_context(agent_name)
                # Enrich — create new details dict with governance key
                enriched_details = {**event["details"], "governance": governance}
                event = AuditEvent(
                    event=event["event"],
                    ts=event["ts"],
                    agent=event["agent"],
                    signer_id=event["signer_id"],
                    details=enriched_details,
                )
            except Exception:
                # Fail-open: enrichment error → forward original event
                logger.warning("Audit enrichment failed for agent '%s'", agent_name, exc_info=True)
        
        await self._downstream.emit(event)
    
    async def _get_governance_context(self, agent_name: str) -> dict:
        # Check cache
        cached = self._cache.get(agent_name)
        if cached and (time.time() - cached[1]) < self._cache_ttl:
            return cached[0]
        
        # Lookup
        record = await self._registry.lookup(agent_name)
        if record is None:
            return {"agent_id": None, "trust_value": None, "trust_tier": None, "owner": None}
        
        governance = {
            "agent_id": record.agent_id,
            "trust_value": record.trust_value,
            "trust_tier": record.trust_tier.value,
            "owner": record.owner,
        }
        self._cache[agent_name] = (governance, time.time())
        return governance
    
    async def flush(self) -> None:
        await self._downstream.flush()
    
    async def close(self) -> None:
        await self._downstream.close()
```

**Re-enrichment guard**: Presidium components (PolicyEngine, CredentialProvider, ApprovalService) emit events that already contain governance context in `details`. The enricher checks for `"governance" in details` and forwards these events without modification. This prevents duplication and avoids overwriting component-specific governance data with the enricher's generic lookup.

---

## Presidium Governance Event Types

All Presidium components emit events through the same pipeline:

| Event Type | Emitter | Key Details |
|---|---|---|
| `policy.evaluated` | PolicyEngine / PEPs | stage, decision, policy_name, resource, action, evaluation_ms |
| `credential.access` | CredentialProvider | credential_name, result (granted/denied), grant_match, backend |
| `approval.requested` | ApprovalService | request_id, resource, action, approvers, timeout_seconds |
| `approval.decided` | ApprovalService | request_id, decision, decided_by, reason, wait_time_seconds |
| `agent.registered` | AgentRegistry | agent_id, revision, owner, grants_count |
| `agent.deregistered` | AgentRegistry | agent_id, reason |
| `status.changed` | AgentRegistry | agent_id, old_status, new_status, trigger |
| `trust.updated` | TrustScorer | agent_id, old_value, new_value, trigger (SUCCESS/FAILURE/POLICY_VIOLATION), old_tier, new_tier |
| `grant.added` | AgentRegistry | agent_id, grant (resources, actions, scope) |
| `grant.removed` | AgentRegistry | agent_id, grant (resources, actions, scope) |

Combined with Civitas's 5 event types (`message.route`, `secret.access`, `tool.call`, `sandbox.exec`, `sandbox.deny`), this gives a total of **15 event types** in the unified audit stream.

---

## Topology YAML Integration

```yaml
# Presidium wraps the Civitas audit sink
presidium:
  audit:
    enrichment: true            # enable governance enrichment (default: true)
    cache_ttl: 5.0              # registry lookup cache TTL in seconds

# Civitas audit sink (downstream — unchanged)
audit:
  sink: jsonl
  path: /var/log/civitas/audit.jsonl
```

**Wiring at startup:**
1. Civitas's `Runtime.from_config()` creates the downstream sink from the `audit:` block
2. Presidium wraps it with `InProcessAuditEnricher(downstream=civitas_sink, registry=registry)`
3. The enricher is injected as the `audit_sink` into `ComponentSet`
4. All Civitas components emit to the enricher; the enricher forwards to the original sink

---

## Civitas Integration Points

| Civitas Component | How AuditEnricher Integrates |
|---|---|
| `AuditSink` protocol | AuditEnricher implements it — drop-in replacement |
| `ComponentSet.audit_sink` | Presidium injects the enricher here |
| `MessageBus.route()` | Emits `message.route` → enricher adds governance context → downstream |
| `AgentProcess.get_credential()` | Emits `secret.access` → enricher adds governance context → downstream |
| `MCPTool.execute()` (fabrica) | Emits `tool.call` → enricher adds governance context → downstream |
| Runtime YAML `audit:` block | Presidium reads this, wraps the sink, injects the enricher |

---

## Design Decisions

| # | Decision | Choice | Alternatives Considered | Rationale |
|---|---|---|---|---|
| E1 | Middleware pattern | Wraps downstream AuditSink | Separate audit pipeline, monkey-patch Civitas | Middleware is clean, no Civitas changes, same pattern as GovernedModelProvider |
| E2 | Fail-open forwarding | Enrichment errors forward original event | Drop event on error, retry enrichment | Audit completeness > enrichment completeness. A raw event is better than no event. |
| E3 | Namespaced enrichment | `details.governance` key | Top-level fields, flat merge | Avoids collisions with Civitas's `sender`, `recipient`, `type` fields |
| E4 | Cached lookups | 5-second TTL dict cache | No cache (per-event lookup), long TTL | 5s balances freshness vs. throughput. MessageBus can emit 1000s of events/second. |
| E5 | Unified pipeline | Civitas + Presidium events in same stream | Separate Presidium audit stream | One log, one OTEL endpoint, one compliance report. Ops simplicity. |

---

## Open Questions (Deferred)

1. **Selective enrichment**: should enrichment be configurable per event type? (M3 — some events may not need governance context)
2. **External platform adapters**: should the enricher support platform-specific transformations (Datadog tags, Splunk fields)? (M3)
3. **Audit event schema versioning**: should events carry a schema version for forward compatibility? (M3)
4. **Tamper-evident chains**: should events be hash-linked for forensic integrity? (M3+)
