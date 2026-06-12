"""InMemoryRegistry — dict-backed AgentRegistry implementation."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from presidium.errors import AgentNotFoundError, GrantNotFoundError
from presidium.model import AgentRecord, AgentStatus, Grant, TrustEvent, TrustTier
from presidium.trust import LinearTrustScore, TrustScorer, tier_for_value


class _TrustEventRecord:
    __slots__ = (
        "agent_id",
        "event",
        "value_before",
        "value_after",
        "tier_before",
        "tier_after",
        "timestamp",
    )

    def __init__(
        self,
        agent_id: str,
        event: TrustEvent,
        value_before: float,
        value_after: float,
        tier_before: TrustTier,
        tier_after: TrustTier,
        timestamp: datetime,
    ) -> None:
        self.agent_id = agent_id
        self.event = event
        self.value_before = value_before
        self.value_after = value_after
        self.tier_before = tier_before
        self.tier_after = tier_after
        self.timestamp = timestamp


class InMemoryRegistry:
    """Dict-backed agent registry with snapshot semantics.

    Every lookup returns a deep copy (snapshot). Mutations via add_grant,
    record_trust_event, etc. increment the revision counter and update
    the updated_at timestamp.

    Trust scoring is delegated to a TrustScorer instance per agent
    (default: LinearTrustScore).
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}
        self._scorers: dict[str, TrustScorer] = {}
        self._trust_events: list[_TrustEventRecord] = []

    def _get_or_raise(self, name: str) -> AgentRecord:
        record = self._agents.get(name)
        if record is None:
            raise AgentNotFoundError(name)
        return record

    def _touch(self, record: AgentRecord) -> None:
        record.revision += 1
        record.updated_at = datetime.now(UTC)

    def _snapshot(self, record: AgentRecord) -> AgentRecord:
        return copy.deepcopy(record)

    def _sync_trust(self, record: AgentRecord) -> None:
        scorer = self._scorers.get(record.name)
        if scorer is not None:
            record.trust_value = scorer.value
            record.trust_tier = scorer.tier

    async def register(self, record: AgentRecord) -> AgentRecord:
        self._agents[record.name] = record
        self._scorers[record.name] = LinearTrustScore(initial_value=record.trust_value)
        self._touch(record)
        return self._snapshot(record)

    async def deregister(self, name: str) -> None:
        self._get_or_raise(name)
        del self._agents[name]
        self._scorers.pop(name, None)

    async def lookup(self, name: str) -> AgentRecord | None:
        record = self._agents.get(name)
        if record is None:
            return None
        self._sync_trust(record)
        return self._snapshot(record)

    async def lookup_by_id(self, agent_id: str) -> AgentRecord | None:
        for record in self._agents.values():
            if record.agent_id == agent_id:
                self._sync_trust(record)
                return self._snapshot(record)
        return None

    async def list_agents(
        self,
        status: AgentStatus | None = None,
        trust_tier: TrustTier | None = None,
        owner: str | None = None,
    ) -> list[AgentRecord]:
        results: list[AgentRecord] = []
        for record in self._agents.values():
            self._sync_trust(record)
            if status is not None and record.status != status:
                continue
            if trust_tier is not None and record.trust_tier != trust_tier:
                continue
            if owner is not None and record.owner != owner:
                continue
            results.append(self._snapshot(record))
        return results

    async def add_grant(self, name: str, grant: Grant) -> AgentRecord:
        record = self._get_or_raise(name)
        record.grants.append(grant)
        self._touch(record)
        self._sync_trust(record)
        return self._snapshot(record)

    async def remove_grant(self, name: str, grant_id: str) -> AgentRecord:
        record = self._get_or_raise(name)
        for i, g in enumerate(record.grants):
            if g.id == grant_id:
                record.grants.pop(i)
                self._touch(record)
                self._sync_trust(record)
                return self._snapshot(record)
        raise GrantNotFoundError(name, grant_id)

    async def has_grant(self, name: str, resource: str, action: str) -> bool:
        record = self._get_or_raise(name)
        return any(resource in g.resources and action in g.actions for g in record.grants)

    async def record_trust_event(self, name: str, event: TrustEvent) -> AgentRecord:
        record = self._get_or_raise(name)
        scorer = self._scorers[record.name]

        value_before = scorer.value
        tier_before = scorer.tier

        scorer.record_event(event)

        value_after = scorer.value
        tier_after = scorer.tier

        self._trust_events.append(
            _TrustEventRecord(
                agent_id=record.agent_id,
                event=event,
                value_before=value_before,
                value_after=value_after,
                tier_before=tier_before,
                tier_after=tier_after,
                timestamp=datetime.now(UTC),
            )
        )

        self._sync_trust(record)
        self._touch(record)
        return self._snapshot(record)

    async def set_trust(self, name: str, value: float, reason: str) -> AgentRecord:
        record = self._get_or_raise(name)
        scorer = self._scorers[record.name]

        value_before = scorer.value
        tier_before = scorer.tier

        if isinstance(scorer, LinearTrustScore):
            scorer.set_value(value)
        else:
            record.trust_value = max(0.0, min(1.0, value))
            record.trust_tier = tier_for_value(record.trust_value)

        value_after = scorer.value if isinstance(scorer, LinearTrustScore) else record.trust_value
        tier_after = scorer.tier if isinstance(scorer, LinearTrustScore) else record.trust_tier

        self._trust_events.append(
            _TrustEventRecord(
                agent_id=record.agent_id,
                event=TrustEvent.HUMAN_OVERRIDE,
                value_before=value_before,
                value_after=value_after,
                tier_before=tier_before,
                tier_after=tier_after,
                timestamp=datetime.now(UTC),
            )
        )

        self._sync_trust(record)
        self._touch(record)
        return self._snapshot(record)

    async def update_status(self, name: str, status: AgentStatus) -> AgentRecord:
        record = self._get_or_raise(name)
        record.status = status
        self._touch(record)
        self._sync_trust(record)
        return self._snapshot(record)
