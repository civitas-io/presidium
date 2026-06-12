from __future__ import annotations

import asyncio

import pytest

from presidium.errors import AgentNotFoundError, GrantNotFoundError
from presidium.model import AgentRecord, AgentStatus, Grant, TrustEvent, TrustTier
from presidium.registry._base import AgentRegistry
from presidium.registry.memory import InMemoryRegistry
from presidium.registry.sqlite import SqliteRegistry

Registry = InMemoryRegistry | SqliteRegistry


def _make_record(
    name: str = "researcher",
    agent_id: str = "presidium://local/researcher",
    trust_value: float = 0.5,
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        name=name,
        public_key="dGVzdC1rZXk=",
        trust_value=trust_value,
        grants=[
            Grant(resources=["tool:database"], actions=["read"], id="g1"),
        ],
        owner="alice@acme.com",
    )


class TestProtocol:
    def test_memory_satisfies_protocol(self) -> None:
        assert isinstance(InMemoryRegistry(), AgentRegistry)

    async def test_sqlite_satisfies_protocol(self) -> None:
        reg = SqliteRegistry(":memory:")
        assert isinstance(reg, AgentRegistry)
        await reg.close()


class TestRegister:
    async def test_register_returns_snapshot(self, registry: Registry) -> None:
        result = await registry.register(_make_record())
        assert result.name == "researcher"
        assert result.revision == 1

    async def test_register_sets_revision(self, registry: Registry) -> None:
        result = await registry.register(_make_record())
        assert result.revision >= 1

    async def test_register_overwrites_existing(self, registry: Registry) -> None:
        await registry.register(_make_record())
        updated = _make_record()
        updated.owner = "bob@acme.com"
        result = await registry.register(updated)
        assert result.owner == "bob@acme.com"


class TestDeregister:
    async def test_deregister_removes_agent(self, registry: Registry) -> None:
        await registry.register(_make_record())
        await registry.deregister("researcher")
        assert await registry.lookup("researcher") is None

    async def test_deregister_nonexistent_raises(self, registry: Registry) -> None:
        with pytest.raises(AgentNotFoundError):
            await registry.deregister("ghost")


class TestLookup:
    async def test_lookup_existing(self, registry: Registry) -> None:
        await registry.register(_make_record())
        result = await registry.lookup("researcher")
        assert result is not None
        assert result.name == "researcher"

    async def test_lookup_nonexistent(self, registry: Registry) -> None:
        assert await registry.lookup("ghost") is None

    async def test_lookup_returns_independent_copy(self, registry: Registry) -> None:
        await registry.register(_make_record())
        snap1 = await registry.lookup("researcher")
        assert snap1 is not None
        snap1.owner = "modified"
        snap2 = await registry.lookup("researcher")
        assert snap2 is not None
        assert snap2.owner == "alice@acme.com"

    async def test_lookup_by_id(self, registry: Registry) -> None:
        await registry.register(_make_record())
        result = await registry.lookup_by_id("presidium://local/researcher")
        assert result is not None
        assert result.name == "researcher"

    async def test_lookup_by_id_nonexistent(self, registry: Registry) -> None:
        assert await registry.lookup_by_id("presidium://local/ghost") is None


class TestListAgents:
    async def test_list_all(self, registry: Registry) -> None:
        await registry.register(_make_record("a", "presidium://local/a"))
        await registry.register(_make_record("b", "presidium://local/b"))
        results = await registry.list_agents()
        assert len(results) == 2

    async def test_filter_by_status(self, registry: Registry) -> None:
        await registry.register(_make_record("a", "presidium://local/a"))
        r2 = _make_record("b", "presidium://local/b")
        r2.status = AgentStatus.RUNNING
        await registry.register(r2)
        results = await registry.list_agents(status=AgentStatus.RUNNING)
        assert len(results) == 1
        assert results[0].name == "b"

    async def test_filter_by_owner(self, registry: Registry) -> None:
        await registry.register(_make_record("a", "presidium://local/a"))
        r2 = _make_record("b", "presidium://local/b")
        r2.owner = "bob@acme.com"
        await registry.register(r2)
        results = await registry.list_agents(owner="bob@acme.com")
        assert len(results) == 1
        assert results[0].name == "b"

    async def test_filter_by_trust_tier(self, registry: Registry) -> None:
        await registry.register(_make_record("a", "presidium://local/a", trust_value=0.8))
        await registry.register(_make_record("b", "presidium://local/b", trust_value=0.2))
        trusted = await registry.list_agents(trust_tier=TrustTier.TRUSTED)
        assert len(trusted) == 1
        assert trusted[0].name == "a"


class TestGrants:
    async def test_add_grant(self, registry: Registry) -> None:
        await registry.register(_make_record())
        new_grant = Grant(resources=["llm:claude"], actions=["invoke"], id="g2")
        result = await registry.add_grant("researcher", new_grant)
        assert len(result.grants) == 2
        assert result.revision > 1

    async def test_remove_grant(self, registry: Registry) -> None:
        await registry.register(_make_record())
        result = await registry.remove_grant("researcher", "g1")
        assert len(result.grants) == 0

    async def test_remove_nonexistent_grant_raises(self, registry: Registry) -> None:
        await registry.register(_make_record())
        with pytest.raises(GrantNotFoundError):
            await registry.remove_grant("researcher", "nonexistent")

    async def test_has_grant_true(self, registry: Registry) -> None:
        await registry.register(_make_record())
        assert await registry.has_grant("researcher", "tool:database", "read") is True

    async def test_has_grant_false(self, registry: Registry) -> None:
        await registry.register(_make_record())
        assert await registry.has_grant("researcher", "tool:database", "write") is False

    async def test_has_grant_nonexistent_agent_raises(self, registry: Registry) -> None:
        with pytest.raises(AgentNotFoundError):
            await registry.has_grant("ghost", "tool:db", "read")


class TestTrustEvents:
    async def test_record_trust_event_updates_value(self, registry: Registry) -> None:
        await registry.register(_make_record())
        result = await registry.record_trust_event("researcher", TrustEvent.SUCCESS)
        assert result.trust_value == pytest.approx(0.52, abs=0.01)

    async def test_record_trust_event_increments_revision(self, registry: Registry) -> None:
        r = await registry.register(_make_record())
        rev_after_register = r.revision
        result = await registry.record_trust_event("researcher", TrustEvent.FAILURE)
        assert result.revision > rev_after_register

    async def test_trust_event_changes_tier(self, registry: Registry) -> None:
        await registry.register(_make_record(trust_value=0.31))
        result = await registry.record_trust_event("researcher", TrustEvent.FAILURE)
        assert result.trust_tier == TrustTier.RESTRICTED

    async def test_set_trust(self, registry: Registry) -> None:
        await registry.register(_make_record())
        result = await registry.set_trust("researcher", 0.9, "manual override")
        assert result.trust_value == pytest.approx(0.9, abs=0.01)
        assert result.trust_tier == TrustTier.TRUSTED

    async def test_record_trust_nonexistent_raises(self, registry: Registry) -> None:
        with pytest.raises(AgentNotFoundError):
            await registry.record_trust_event("ghost", TrustEvent.SUCCESS)


class TestInMemoryTrustEventsHistory:
    async def test_trust_events_appended(self) -> None:
        reg = InMemoryRegistry()
        await reg.register(_make_record())
        await reg.record_trust_event("researcher", TrustEvent.SUCCESS)
        await reg.record_trust_event("researcher", TrustEvent.FAILURE)
        assert len(reg._trust_events) == 2
        assert reg._trust_events[0].event == TrustEvent.SUCCESS
        assert reg._trust_events[1].event == TrustEvent.FAILURE


class TestUpdateStatus:
    async def test_update_status(self, registry: Registry) -> None:
        await registry.register(_make_record())
        result = await registry.update_status("researcher", AgentStatus.RUNNING)
        assert result.status == AgentStatus.RUNNING

    async def test_update_status_nonexistent_raises(self, registry: Registry) -> None:
        with pytest.raises(AgentNotFoundError):
            await registry.update_status("ghost", AgentStatus.RUNNING)


class TestConcurrency:
    async def test_concurrent_writers(self, registry: Registry) -> None:
        await registry.register(_make_record())

        async def add_grant(i: int) -> None:
            grant = Grant(resources=[f"tool:t{i}"], actions=["read"], id=f"cg-{i}")
            await registry.add_grant("researcher", grant)

        await asyncio.gather(*(add_grant(i) for i in range(100)))

        result = await registry.lookup("researcher")
        assert result is not None
        assert len(result.grants) == 101
