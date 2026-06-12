from __future__ import annotations

import pytest

from presidium.audit import AuditEnricher, AuditEvent, AuditSink, InProcessAuditEnricher
from presidium.model import AgentRecord, AgentStatus, TrustTier
from presidium.registry.memory import InMemoryRegistry


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        pass


def _make_event(agent: str = "researcher", event_type: str = "message.route") -> AuditEvent:
    return {
        "event": event_type,
        "ts": "2026-06-11T10:00:00Z",
        "agent": agent,
        "signer_id": agent,
        "details": {"sender": agent, "recipient": "tool", "type": "tool_call"},
    }


async def _setup_registry(name: str = "researcher") -> InMemoryRegistry:
    reg = InMemoryRegistry()
    await reg.register(
        AgentRecord(
            agent_id="presidium://acme.com/prod/researcher",
            name=name,
            public_key="a2V5",
            trust_value=0.72,
            trust_tier=TrustTier.TRUSTED,
            owner="alice@acme.com",
            status=AgentStatus.RUNNING,
        )
    )
    return reg


class TestInProcessAuditEnricherProtocol:
    def test_satisfies_audit_enricher(self) -> None:
        sink = RecordingSink()
        reg = InMemoryRegistry()
        enricher = InProcessAuditEnricher(sink, reg)
        assert isinstance(enricher, AuditEnricher)

    def test_satisfies_audit_sink(self) -> None:
        sink = RecordingSink()
        reg = InMemoryRegistry()
        enricher = InProcessAuditEnricher(sink, reg)
        assert isinstance(enricher, AuditSink)


class TestEnrichment:
    async def test_enriches_with_governance_data(self) -> None:
        sink = RecordingSink()
        reg = await _setup_registry()
        enricher = InProcessAuditEnricher(sink, reg)

        await enricher.emit(_make_event())

        assert len(sink.events) == 1
        gov = sink.events[0]["details"]["governance"]
        assert gov["agent_id"] == "presidium://acme.com/prod/researcher"
        assert gov["trust_value"] == pytest.approx(0.72, abs=0.01)
        assert gov["trust_tier"] == "trusted"
        assert gov["owner"] == "alice@acme.com"

    async def test_preserves_original_details(self) -> None:
        sink = RecordingSink()
        reg = await _setup_registry()
        enricher = InProcessAuditEnricher(sink, reg)

        await enricher.emit(_make_event())

        details = sink.events[0]["details"]
        assert details["sender"] == "researcher"
        assert details["recipient"] == "tool"

    async def test_unknown_agent_forwards_unenriched(self) -> None:
        sink = RecordingSink()
        reg = InMemoryRegistry()
        enricher = InProcessAuditEnricher(sink, reg)

        await enricher.emit(_make_event(agent="unknown"))

        assert len(sink.events) == 1
        assert "governance" not in sink.events[0].get("details", {})

    async def test_empty_agent_forwards_unenriched(self) -> None:
        sink = RecordingSink()
        reg = await _setup_registry()
        enricher = InProcessAuditEnricher(sink, reg)

        event = _make_event()
        event["agent"] = ""
        await enricher.emit(event)

        assert len(sink.events) == 1
        assert "governance" not in sink.events[0].get("details", {})


class TestReEnrichmentGuard:
    async def test_existing_governance_not_overwritten(self) -> None:
        sink = RecordingSink()
        reg = await _setup_registry()
        enricher = InProcessAuditEnricher(sink, reg)

        event = _make_event()
        event["details"]["governance"] = {"agent_id": "original", "custom": True}
        await enricher.emit(event)

        assert len(sink.events) == 1
        gov = sink.events[0]["details"]["governance"]
        assert gov["agent_id"] == "original"
        assert gov["custom"] is True


class TestCaching:
    async def test_cache_prevents_repeated_lookups(self) -> None:
        sink = RecordingSink()
        reg = await _setup_registry()
        enricher = InProcessAuditEnricher(sink, reg, cache_ttl=10.0)

        await enricher.emit(_make_event())
        await enricher.emit(_make_event())

        assert len(sink.events) == 2
        assert sink.events[0]["details"]["governance"] == sink.events[1]["details"]["governance"]

    async def test_cache_expires(self) -> None:
        sink = RecordingSink()
        reg = await _setup_registry()
        enricher = InProcessAuditEnricher(sink, reg, cache_ttl=0.0)

        await enricher.emit(_make_event())
        await enricher.emit(_make_event())

        assert len(sink.events) == 2


class TestFailOpen:
    async def test_enrichment_error_forwards_original(self) -> None:
        sink = RecordingSink()

        class BrokenRegistry(InMemoryRegistry):
            async def lookup(self, name: str) -> AgentRecord | None:
                raise RuntimeError("registry down")

        reg = BrokenRegistry()
        enricher = InProcessAuditEnricher(sink, reg)

        await enricher.emit(_make_event())

        assert len(sink.events) == 1
        assert "governance" not in sink.events[0].get("details", {})


class TestFlushAndClose:
    async def test_flush_delegates(self) -> None:
        sink = RecordingSink()
        reg = InMemoryRegistry()
        enricher = InProcessAuditEnricher(sink, reg)
        await enricher.flush()

    async def test_close_delegates(self) -> None:
        sink = RecordingSink()
        reg = InMemoryRegistry()
        enricher = InProcessAuditEnricher(sink, reg)
        await enricher.close()
