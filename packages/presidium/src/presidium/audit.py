"""AuditEnricher Protocol and InProcessAuditEnricher."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol, runtime_checkable

from presidium.registry._base import AgentRegistry

logger = logging.getLogger(__name__)

AuditEvent = dict[str, Any]


@runtime_checkable
class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...
    async def flush(self) -> None: ...
    async def close(self) -> None: ...


@runtime_checkable
class AuditEnricher(Protocol):
    """Structural subtype of AuditSink that adds governance context."""

    async def emit(self, event: AuditEvent) -> None: ...
    async def flush(self) -> None: ...
    async def close(self) -> None: ...


class _CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: dict[str, Any], expires_at: float) -> None:
        self.data = data
        self.expires_at = expires_at


class InProcessAuditEnricher:
    """Middleware wrapping a downstream AuditSink with governance enrichment.

    Looks up the agent in the registry, adds ``details["governance"]``
    with trust value, tier, owner, and agent_id. Uses a TTL cache to
    avoid repeated registry lookups.

    Fail-open: enrichment errors forward the original event unchanged.
    Re-enrichment guard: events with existing ``governance`` key are
    forwarded without modification.
    """

    def __init__(
        self,
        downstream: AuditSink,
        registry: AgentRegistry,
        cache_ttl: float = 5.0,
    ) -> None:
        self._downstream = downstream
        self._registry = registry
        self._cache_ttl = cache_ttl
        self._cache: dict[str, _CacheEntry] = {}

    async def _get_governance_data(self, agent_name: str) -> dict[str, Any] | None:
        now = time.monotonic()
        entry = self._cache.get(agent_name)
        if entry is not None and now < entry.expires_at:
            return entry.data

        record = await self._registry.lookup(agent_name)
        if record is None:
            return None

        data: dict[str, Any] = {
            "agent_id": record.agent_id,
            "trust_value": record.trust_value,
            "trust_tier": record.trust_tier.value,
            "owner": record.owner,
        }
        self._cache[agent_name] = _CacheEntry(data, now + self._cache_ttl)
        return data

    async def emit(self, event: AuditEvent) -> None:
        details = event.get("details")
        if isinstance(details, dict) and "governance" in details:
            await self._downstream.emit(event)
            return

        agent_name = event.get("agent", "")
        if agent_name:
            try:
                gov_data = await self._get_governance_data(agent_name)
                if gov_data is not None:
                    enriched = dict(event)
                    enriched_details = dict(details) if isinstance(details, dict) else {}
                    enriched_details["governance"] = gov_data
                    enriched["details"] = enriched_details
                    await self._downstream.emit(enriched)
                    return
            except Exception:
                logger.exception("Enrichment failed for agent=%s, forwarding original", agent_name)

        await self._downstream.emit(event)

    async def flush(self) -> None:
        await self._downstream.flush()

    async def close(self) -> None:
        await self._downstream.close()
