"""AgentRegistry Protocol definition."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from presidium.model import AgentRecord, AgentStatus, Grant, TrustEvent, TrustTier


@runtime_checkable
class AgentRegistry(Protocol):
    """Protocol for the agent identity store.

    Snapshot semantics: lookup() returns an immutable snapshot of the
    AgentRecord at the time of the call. Mutations after lookup do not
    affect previously returned snapshots.
    """

    async def register(self, record: AgentRecord) -> AgentRecord: ...

    async def deregister(self, name: str) -> None: ...

    async def lookup(self, name: str) -> AgentRecord | None: ...

    async def lookup_by_id(self, agent_id: str) -> AgentRecord | None: ...

    async def list_agents(
        self,
        status: AgentStatus | None = None,
        trust_tier: TrustTier | None = None,
        owner: str | None = None,
    ) -> list[AgentRecord]: ...

    async def add_grant(self, name: str, grant: Grant) -> AgentRecord: ...

    async def remove_grant(self, name: str, grant_id: str) -> AgentRecord: ...

    async def has_grant(self, name: str, resource: str, action: str) -> bool: ...

    async def record_trust_event(self, name: str, event: TrustEvent) -> AgentRecord: ...

    async def set_trust(self, name: str, value: float, reason: str) -> AgentRecord: ...

    async def update_status(self, name: str, status: AgentStatus) -> AgentRecord: ...
