"""Registry-level integration tests for trust ceiling propagation and
monotonic capability narrowing (2026-08-22) -- exercised against both real
registry backends via the shared ``registry`` fixture (InMemoryRegistry,
SqliteRegistry), not just the pure functions in presidium.lineage.
"""

from __future__ import annotations

import pytest

from presidium.errors import (
    DelegationDepthExceededError,
    GrantEscalationError,
    UnresolvableParentError,
)
from presidium.model import AgentRecord, Grant, TrustEvent
from presidium.registry.memory import InMemoryRegistry
from presidium.registry.sqlite import SqliteRegistry

Registry = InMemoryRegistry | SqliteRegistry


def _agent(
    name: str,
    trust_value: float = 0.5,
    parent_agent_id: str | None = None,
    trust_ceiling: float | None = None,
    grants: list[Grant] | None = None,
) -> AgentRecord:
    return AgentRecord(
        agent_id=f"presidium://local/{name}",
        name=name,
        public_key="",
        trust_value=trust_value,
        parent_agent_id=parent_agent_id,
        trust_ceiling=trust_ceiling,
        grants=grants or [],
    )


class TestTrustCeilingAtRegistration:
    async def test_top_level_agent_has_no_ceiling(self, registry: Registry) -> None:
        parent = await registry.register(_agent("parent", trust_value=0.9))
        assert parent.trust_ceiling is None
        assert parent.depth == 0

    async def test_child_ceiling_derived_from_parent_trust(self, registry: Registry) -> None:
        await registry.register(_agent("parent", trust_value=0.6))
        child = await registry.register(
            _agent("child", trust_value=0.5, parent_agent_id="presidium://local/parent")
        )
        assert child.trust_ceiling == pytest.approx(0.6)
        assert child.depth == 1

    async def test_the_real_trust_washing_attack_is_blocked(self, registry: Registry) -> None:
        """The exact scenario this whole feature exists to close: an agent
        (or a compromised orchestrator) degraded by policy violations can no
        longer launder itself into a fresh, fully-trusted "child" registered
        under the same lineage."""
        await registry.register(_agent("orchestrator", trust_value=0.1))
        child = await registry.register(
            _agent(
                "fresh-replacement",
                trust_value=0.7,  # optimistic cold start, requested by the caller
                parent_agent_id="presidium://local/orchestrator",
            )
        )
        assert child.trust_value <= 0.1 + 1e-9
        assert child.trust_ceiling == pytest.approx(0.1)

    async def test_requested_ceiling_narrower_than_parent_is_honored(
        self, registry: Registry
    ) -> None:
        await registry.register(_agent("parent", trust_value=0.9))
        child = await registry.register(
            _agent(
                "child",
                trust_value=0.1,
                parent_agent_id="presidium://local/parent",
                trust_ceiling=0.2,
            )
        )
        assert child.trust_ceiling == pytest.approx(0.2)

    async def test_ceiling_holds_after_success_events(self, registry: Registry) -> None:
        await registry.register(_agent("orchestrator", trust_value=0.1))
        await registry.register(
            _agent("child", trust_value=0.1, parent_agent_id="presidium://local/orchestrator")
        )
        for _ in range(20):
            await registry.record_trust_event("child", TrustEvent.SUCCESS)
        record = await registry.lookup("child")
        assert record is not None
        assert record.trust_value <= 0.1 + 1e-9

    async def test_dangling_parent_agent_id_rejected(self, registry: Registry) -> None:
        with pytest.raises(UnresolvableParentError, match="presidium://local/ghost"):
            await registry.register(_agent("child", parent_agent_id="presidium://local/ghost"))

    async def test_multi_hop_chain_is_transitive(self, registry: Registry) -> None:
        await registry.register(_agent("grandparent", trust_value=0.8))
        await registry.register(
            _agent("parent", trust_value=0.95, parent_agent_id="presidium://local/grandparent")
        )
        grandchild = await registry.register(
            _agent("grandchild", trust_value=0.95, parent_agent_id="presidium://local/parent")
        )
        assert grandchild.trust_ceiling == pytest.approx(0.8)
        assert grandchild.depth == 2


class TestGrantNarrowingAtRegistration:
    async def test_child_subset_of_parent_grants_allowed(self, registry: Registry) -> None:
        await registry.register(
            _agent("parent", grants=[Grant(resources=["tool:db"], actions=["read", "write"])])
        )
        child = await registry.register(
            _agent(
                "child",
                parent_agent_id="presidium://local/parent",
                grants=[Grant(resources=["tool:db"], actions=["read"])],
            )
        )
        assert child.grants[0].actions == ["read"]

    async def test_the_real_grant_escalation_hole_is_blocked(self, registry: Registry) -> None:
        """A spawned child can no longer end up with more grants than its
        parent -- the real, open security hole this closes."""
        await registry.register(
            _agent("parent", grants=[Grant(resources=["tool:read_db"], actions=["read"])])
        )
        with pytest.raises(GrantEscalationError, match="tool:admin_delete_everything"):
            await registry.register(
                _agent(
                    "child",
                    parent_agent_id="presidium://local/parent",
                    grants=[Grant(resources=["tool:admin_delete_everything"], actions=["invoke"])],
                )
            )

    async def test_top_level_agent_is_never_narrowing_checked(self, registry: Registry) -> None:
        """No parent_agent_id means no lineage check at all -- broad grants
        for a genuinely top-level agent are unaffected."""
        agent = await registry.register(
            _agent("standalone", grants=[Grant(resources=["tool:admin"], actions=["invoke"])])
        )
        assert agent.grants[0].resources == ["tool:admin"]


class TestGrantNarrowingOnAddGrant:
    async def test_narrow_add_grant_allowed(self, registry: Registry) -> None:
        await registry.register(
            _agent("parent", grants=[Grant(resources=["tool:db"], actions=["read", "write"])])
        )
        await registry.register(_agent("child", parent_agent_id="presidium://local/parent"))
        updated = await registry.add_grant("child", Grant(resources=["tool:db"], actions=["read"]))
        assert len(updated.grants) == 1

    async def test_escalating_add_grant_rejected(self, registry: Registry) -> None:
        await registry.register(_agent("parent"))
        await registry.register(_agent("child", parent_agent_id="presidium://local/parent"))
        with pytest.raises(GrantEscalationError):
            await registry.add_grant("child", Grant(resources=["tool:admin"], actions=["invoke"]))

    async def test_add_grant_on_top_level_agent_unaffected(self, registry: Registry) -> None:
        await registry.register(_agent("standalone"))
        updated = await registry.add_grant(
            "standalone", Grant(resources=["tool:anything"], actions=["invoke"])
        )
        assert len(updated.grants) == 1


class TestDelegationDepthLimit:
    async def test_depth_increments_across_a_real_chain(self, registry: Registry) -> None:
        prev_name = "gen0"
        await registry.register(_agent(prev_name))
        for i in range(1, 5):
            name = f"gen{i}"
            record = await registry.register(
                _agent(name, parent_agent_id=f"presidium://local/{prev_name}")
            )
            assert record.depth == i
            prev_name = name

    async def test_exceeding_default_max_depth_rejected(self, registry: Registry) -> None:
        # gen0 (depth 0) through gen10 (depth 10) are all within the default
        # max_delegation_depth=10 -- gen11 (depth 11) is the first rejection.
        prev_name = "gen0"
        await registry.register(_agent(prev_name))
        for i in range(1, 11):
            name = f"gen{i}"
            record = await registry.register(
                _agent(name, parent_agent_id=f"presidium://local/{prev_name}")
            )
            assert record.depth == i
            prev_name = name
        with pytest.raises(DelegationDepthExceededError):
            await registry.register(
                _agent("gen11", parent_agent_id=f"presidium://local/{prev_name}")
            )


class TestConfigurableMaxDelegationDepth:
    async def test_custom_max_delegation_depth_on_memory_registry(self) -> None:
        reg = InMemoryRegistry(max_delegation_depth=1)
        await reg.register(_agent("parent"))
        await reg.register(_agent("child", parent_agent_id="presidium://local/parent"))
        with pytest.raises(DelegationDepthExceededError):
            await reg.register(_agent("grandchild", parent_agent_id="presidium://local/child"))

    async def test_custom_max_delegation_depth_on_sqlite_registry(self) -> None:
        reg = SqliteRegistry(":memory:", max_delegation_depth=1)
        try:
            await reg.register(_agent("parent"))
            await reg.register(_agent("child", parent_agent_id="presidium://local/parent"))
            with pytest.raises(DelegationDepthExceededError):
                await reg.register(_agent("grandchild", parent_agent_id="presidium://local/child"))
        finally:
            await reg.close()
