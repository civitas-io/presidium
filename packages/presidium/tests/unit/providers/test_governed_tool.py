from __future__ import annotations

import pytest

from presidium.approval import CallbackApprovalProvider
from presidium.errors import PolicyDeniedError
from presidium.model import (
    AgentRecord,
    AgentStatus,
    EnforcementMode,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine
from presidium.providers.tool import GovernedToolProvider
from presidium.registry.memory import InMemoryRegistry
from tests.policy_fixtures import ALLOW_ALL


async def _setup() -> tuple[InMemoryRegistry, CelPolicyEngine]:
    reg = InMemoryRegistry()
    await reg.register(
        AgentRecord(
            agent_id="presidium://local/test",
            name="test",
            public_key="a2V5",
            trust_value=0.5,
            trust_tier=TrustTier.STANDARD,
            grants=[Grant(resources=["tool:database"], actions=["read"], id="g1")],
            owner="alice@acme.com",
            status=AgentStatus.RUNNING,
        )
    )
    engine = CelPolicyEngine()
    return reg, engine


DENY_NO_GRANT = PolicyRule(
    name="enforce-grants",
    stage=EvaluationStage.PRE_TOOL,
    expression="""
        !agent.grants.exists(g,
            request.resource in g.resources &&
            request.action in g.actions
        )
    """,
    decision=PolicyDecision.DENY,
    reason="No matching grant",
    priority=100,
)

TRUST_GATE = PolicyRule(
    name="trust-gate",
    stage=EvaluationStage.PRE_TOOL,
    expression='request.action == "write" && agent.trust.value < 0.7',
    decision=PolicyDecision.REQUIRE_APPROVAL,
    reason="Low trust write",
    approvers=("security@acme.com",),
    priority=90,
)

ADVISORY_DENY = PolicyRule(
    name="advisory",
    stage=EvaluationStage.PRE_TOOL,
    expression="true",
    decision=PolicyDecision.DENY,
    priority=50,
    enforcement=EnforcementMode.ADVISORY,
)


class TestGovernedToolProviderAllow:
    async def test_allow_with_matching_grant(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT, ALLOW_ALL])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check("test", "database", "read")
        assert result.decision == PolicyDecision.ALLOW

    async def test_denied_when_no_rules_real_default_2026_08_24(self) -> None:
        """Real, current behavior -- check() raises PolicyDeniedError now,
        matching the new default-deny fallback (docs/design/policy-engine.md
        P5), not a patched-to-keep-passing artifact."""
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedToolProvider(engine, reg)
        with pytest.raises(PolicyDeniedError):
            await provider.check("test", "database")


class TestGovernedToolProviderDeny:
    async def test_deny_without_grant(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT])
        provider = GovernedToolProvider(engine, reg)
        with pytest.raises(PolicyDeniedError) as exc_info:
            await provider.check("test", "web_search")
        assert exc_info.value.policy_name == "enforce-grants"

    async def test_deny_wrong_action(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT])
        provider = GovernedToolProvider(engine, reg)
        with pytest.raises(PolicyDeniedError):
            await provider.check("test", "database", "write")

    async def test_deny_nonexistent_agent(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedToolProvider(engine, reg)
        with pytest.raises(PolicyDeniedError):
            await provider.check("ghost", "database")


class TestGovernedToolProviderApproval:
    async def test_require_approval_auto_approve(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([TRUST_GATE])
        approval = CallbackApprovalProvider(auto_approve=True)
        provider = GovernedToolProvider(engine, reg, approval=approval)
        result = await provider.check("test", "database", "write")
        assert result.decision == PolicyDecision.REQUIRE_APPROVAL

    async def test_require_approval_denied(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([TRUST_GATE])
        approval = CallbackApprovalProvider(auto_deny=True)
        provider = GovernedToolProvider(engine, reg, approval=approval)
        with pytest.raises(PolicyDeniedError, match="Approval denied"):
            await provider.check("test", "database", "write")

    async def test_no_approval_service_raises(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([TRUST_GATE])
        provider = GovernedToolProvider(engine, reg)
        with pytest.raises(PolicyDeniedError, match="no ApprovalService"):
            await provider.check("test", "database", "write")


SOFT_DENY = PolicyRule(
    name="soft",
    stage=[EvaluationStage.PRE_TOOL, EvaluationStage.POST_TOOL],
    expression="true",
    decision=PolicyDecision.DENY,
    priority=50,
    enforcement=EnforcementMode.SOFT,
)


class TestGovernedToolProviderEnforcementModes:
    """Real, pre-existing coverage gap closed alongside the check_grant() work
    (found while re-running coverage on this same file, not introduced by it):
    the SOFT branch (mirroring the already-tested ADVISORY one) was never
    exercised.
    """

    async def test_advisory_does_not_block(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([ADVISORY_DENY])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check("test", "database")
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.ADVISORY

    async def test_soft_does_not_block(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([SOFT_DENY])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check("test", "database")
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.SOFT


class TestGovernedToolProviderCheckGrant:
    """check_grant() -- never blocks, never raises. See docs/design/
    presidium-server.md for the real, first consumer of this method.

    Real, important difference from check(): ``resource`` is used exactly as
    given, NOT prefixed with ``"tool:"`` the way check()'s ``tool`` parameter
    is (found and fixed during implementation -- an earlier draft shared
    check()'s own auto-prefixing helper, which silently broke
    presidium-server-requirements.md's FR-1.3 "verbatim" requirement). These
    tests pass fully-qualified resource strings ("tool:database") to match
    the shared fixture's own grant (also "tool:database"), exactly the way a
    real caller must.
    """

    async def test_allow_returned_as_value(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT, ALLOW_ALL])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check_grant("test", "tool:database", "read")
        assert result.decision == PolicyDecision.ALLOW

    async def test_deny_returned_as_value_not_raised(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check_grant("test", "tool:web_search")
        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "enforce-grants"

    async def test_resource_used_verbatim_not_prefixed(self) -> None:
        """The real, specific behavior this whole class exists to prove: an
        unprefixed resource string is used exactly as given, so it does NOT
        match a grant scoped to "tool:database" -- confirming check_grant()
        genuinely does not add the "tool:" prefix check() does.
        """
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check_grant("test", "database", "read")
        assert result.decision == PolicyDecision.DENY

    async def test_require_approval_returned_immediately_not_blocked(self) -> None:
        """The core, real behavioral difference from check(): no
        ApprovalService is even configured here, and this must NOT raise
        'no ApprovalService configured' the way check() does -- it must
        just return the REQUIRE_APPROVAL decision as a value.
        """
        reg, engine = await _setup()
        engine.load_policies([TRUST_GATE])
        provider = GovernedToolProvider(engine, reg)  # no approval= at all
        result = await provider.check_grant("test", "tool:database", "write")
        assert result.decision == PolicyDecision.REQUIRE_APPROVAL
        assert result.approvers == ["security@acme.com"]

    async def test_require_approval_ignores_configured_approval_service(self) -> None:
        """Even if an ApprovalService IS configured (e.g. because the same
        GovernedToolProvider is also used via check() elsewhere), check_grant()
        must never call it -- confirmed via auto_deny, which would make
        check() raise "Approval denied", not return REQUIRE_APPROVAL.
        """
        reg, engine = await _setup()
        engine.load_policies([TRUST_GATE])
        approval = CallbackApprovalProvider(auto_deny=True)
        provider = GovernedToolProvider(engine, reg, approval=approval)
        result = await provider.check_grant("test", "tool:database", "write")
        assert result.decision == PolicyDecision.REQUIRE_APPROVAL

    async def test_unresolvable_agent_returns_deny_not_raise(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check_grant("ghost", "tool:database")
        assert result.decision == PolicyDecision.DENY
        assert result.reason == "Agent not found in registry"

    async def test_unresolvable_agent_emits_no_audit_event(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        sink = _RecordingSink()
        provider = GovernedToolProvider(engine, reg, audit_sink=sink)  # type: ignore[arg-type]
        await provider.check_grant("ghost", "tool:database")
        assert sink.events == []

    async def test_emits_audit_event_for_a_resolvable_agent(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        sink = _RecordingSink()
        provider = GovernedToolProvider(engine, reg, audit_sink=sink)  # type: ignore[arg-type]
        await provider.check_grant("test", "database")
        assert len(sink.events) == 1
        assert sink.events[0]["event"] == "policy.evaluated"


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def emit(self, event: dict[str, object]) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        pass


class TestGovernedToolProviderAudit:
    async def test_emits_audit_event(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([ALLOW_ALL])
        sink = _RecordingSink()
        provider = GovernedToolProvider(engine, reg, audit_sink=sink)  # type: ignore[arg-type]
        await provider.check("test", "database")
        assert len(sink.events) == 1
        assert sink.events[0]["event"] == "policy.evaluated"
        details = sink.events[0]["details"]
        assert isinstance(details, dict)
        assert details["stage"] == "pre_tool"


BLOCK_LARGE_RESULTS = PolicyRule(
    name="block-large-results",
    stage=EvaluationStage.POST_TOOL,
    expression="result.size_bytes > 100000",
    decision=PolicyDecision.DENY,
    reason="Result exceeds size limit",
    priority=80,
)


class TestGovernedToolProviderPostCheck:
    async def test_post_check_allows_small_result(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([BLOCK_LARGE_RESULTS, ALLOW_ALL])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.post_check("test", "database", "read", {"size_bytes": 500})
        assert result.decision == PolicyDecision.ALLOW

    async def test_post_check_denies_large_result(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([BLOCK_LARGE_RESULTS])
        provider = GovernedToolProvider(engine, reg)
        with pytest.raises(PolicyDeniedError, match="size limit"):
            await provider.post_check("test", "database", "read", {"size_bytes": 200000})

    async def test_post_check_nonexistent_agent_raises(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedToolProvider(engine, reg)
        with pytest.raises(PolicyDeniedError):
            await provider.post_check("ghost", "database", "read", {})

    async def test_post_check_advisory_soft_does_not_raise(self) -> None:
        """Real, pre-existing coverage gap closed alongside the check_grant()
        work: post_check()'s ADVISORY/SOFT early-return branch was never
        exercised."""
        reg, engine = await _setup()
        engine.load_policies([SOFT_DENY])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.post_check("test", "database", "read", {})
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.SOFT
