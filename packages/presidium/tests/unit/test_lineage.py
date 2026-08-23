"""Tests for presidium.lineage -- trust ceiling propagation and monotonic
capability narrowing, surfaced by a direct comparison against Microsoft's
Agent Governance Toolkit (2026-08-22)."""

from __future__ import annotations

import pytest

from presidium.errors import DelegationDepthExceededError, GrantEscalationError
from presidium.lineage import (
    DEFAULT_MAX_DELEGATION_DEPTH,
    compute_child_ceiling,
    compute_child_depth,
    validate_grant_narrowing,
)
from presidium.model import AgentRecord, Grant


def _make_agent(
    name: str = "parent",
    trust_value: float = 0.5,
    trust_ceiling: float | None = None,
    depth: int = 0,
    grants: list[Grant] | None = None,
) -> AgentRecord:
    return AgentRecord(
        agent_id=f"presidium://local/{name}",
        name=name,
        public_key="",
        trust_value=trust_value,
        trust_ceiling=trust_ceiling,
        depth=depth,
        grants=grants or [],
    )


class TestComputeChildCeiling:
    def test_uncapped_parent_and_no_request_defaults_to_parent_trust_value(self) -> None:
        parent = _make_agent(trust_value=0.6)
        assert compute_child_ceiling(parent, None) == pytest.approx(0.6)

    def test_never_exceeds_parent_trust_value(self) -> None:
        """The real trust-washing scenario: a degraded parent can't produce
        a fully-trusted, freshly-registered child."""
        parent = _make_agent(trust_value=0.1)
        assert compute_child_ceiling(parent, requested_ceiling=1.0) == pytest.approx(0.1)

    def test_never_exceeds_parents_own_ceiling(self) -> None:
        parent = _make_agent(trust_value=0.9, trust_ceiling=0.3)
        assert compute_child_ceiling(parent, requested_ceiling=1.0) == pytest.approx(0.3)

    def test_requested_ceiling_can_narrow_further(self) -> None:
        parent = _make_agent(trust_value=0.9)
        assert compute_child_ceiling(parent, requested_ceiling=0.2) == pytest.approx(0.2)

    def test_requested_ceiling_cannot_widen_beyond_parent(self) -> None:
        parent = _make_agent(trust_value=0.4)
        assert compute_child_ceiling(parent, requested_ceiling=0.9) == pytest.approx(0.4)

    def test_transitive_across_a_chain(self) -> None:
        """Grandchild's ceiling only ever needs its immediate parent's
        already-computed, already-persisted values -- no chain-walking."""
        grandparent = _make_agent(name="gp", trust_value=0.8)
        parent_ceiling = compute_child_ceiling(grandparent, None)
        parent = _make_agent(name="p", trust_value=0.95, trust_ceiling=parent_ceiling)
        grandchild_ceiling = compute_child_ceiling(parent, None)
        assert grandchild_ceiling == pytest.approx(0.8)

    def test_never_negative(self) -> None:
        parent = _make_agent(trust_value=0.0)
        assert compute_child_ceiling(parent, None) >= 0.0


class TestValidateGrantNarrowing:
    def test_subset_grants_allowed(self) -> None:
        parent = _make_agent(grants=[Grant(resources=["tool:database"], actions=["read", "write"])])
        child_grants = [Grant(resources=["tool:database"], actions=["read"])]
        validate_grant_narrowing(parent, "child", child_grants)  # must not raise

    def test_identical_grants_allowed(self) -> None:
        parent = _make_agent(grants=[Grant(resources=["tool:database"], actions=["read"])])
        child_grants = [Grant(resources=["tool:database"], actions=["read"])]
        validate_grant_narrowing(parent, "child", child_grants)  # must not raise

    def test_no_grants_always_allowed(self) -> None:
        parent = _make_agent(grants=[Grant(resources=["tool:database"], actions=["read"])])
        validate_grant_narrowing(parent, "child", [])  # must not raise

    def test_escalation_beyond_parent_rejected(self) -> None:
        """The real, open security hole this closes: a child ending up with
        more grants than its parent."""
        parent = _make_agent(grants=[Grant(resources=["tool:read_db"], actions=["read"])])
        child_grants = [Grant(resources=["tool:admin_delete_everything"], actions=["invoke"])]
        with pytest.raises(GrantEscalationError, match="tool:admin_delete_everything"):
            validate_grant_narrowing(parent, "child", child_grants)

    def test_escalation_error_names_the_agents(self) -> None:
        parent = _make_agent(name="orchestrator")
        with pytest.raises(GrantEscalationError) as exc_info:
            validate_grant_narrowing(
                parent, "rogue-child", [Grant(resources=["tool:x"], actions=["invoke"])]
            )
        assert exc_info.value.agent_name == "rogue-child"
        assert exc_info.value.parent_name == "orchestrator"
        assert exc_info.value.excess == ["tool:x:invoke"]

    def test_partial_escalation_one_grant_ok_one_not(self) -> None:
        parent = _make_agent(grants=[Grant(resources=["tool:database"], actions=["read"])])
        child_grants = [
            Grant(resources=["tool:database"], actions=["read"]),
            Grant(resources=["tool:admin"], actions=["write"]),
        ]
        with pytest.raises(GrantEscalationError, match="tool:admin:write"):
            validate_grant_narrowing(parent, "child", child_grants)

    def test_action_widening_on_same_resource_rejected(self) -> None:
        """Parent can read; child requesting write on the same resource is
        still an escalation even though the resource string matches."""
        parent = _make_agent(grants=[Grant(resources=["tool:database"], actions=["read"])])
        child_grants = [Grant(resources=["tool:database"], actions=["read", "write"])]
        with pytest.raises(GrantEscalationError, match="tool:database:write"):
            validate_grant_narrowing(parent, "child", child_grants)


class TestComputeChildDepth:
    def test_top_level_parent_gives_depth_one(self) -> None:
        parent = _make_agent(depth=0)
        assert compute_child_depth(parent, "child") == 1

    def test_depth_increments_transitively(self) -> None:
        parent = _make_agent(depth=4)
        assert compute_child_depth(parent, "child") == 5

    def test_default_max_depth_is_ten(self) -> None:
        assert DEFAULT_MAX_DELEGATION_DEPTH == 10

    def test_depth_at_the_limit_allowed(self) -> None:
        parent = _make_agent(depth=8)
        assert compute_child_depth(parent, "child", max_depth=9) == 9

    def test_depth_exceeding_limit_rejected(self) -> None:
        parent = _make_agent(depth=9)
        with pytest.raises(DelegationDepthExceededError) as exc_info:
            compute_child_depth(parent, "child", max_depth=9)
        assert exc_info.value.depth == 10
        assert exc_info.value.max_depth == 9
        assert exc_info.value.agent_name == "child"

    def test_default_max_depth_enforced_when_not_overridden(self) -> None:
        parent = _make_agent(depth=DEFAULT_MAX_DELEGATION_DEPTH)
        with pytest.raises(DelegationDepthExceededError):
            compute_child_depth(parent, "child")
