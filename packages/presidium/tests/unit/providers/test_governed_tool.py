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
        engine.load_policies([DENY_NO_GRANT])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check("test", "database", "read")
        assert result.decision == PolicyDecision.ALLOW

    async def test_allow_when_no_rules(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check("test", "database")
        assert result.decision == PolicyDecision.ALLOW


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


class TestGovernedToolProviderEnforcementModes:
    async def test_advisory_does_not_block(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([ADVISORY_DENY])
        provider = GovernedToolProvider(engine, reg)
        result = await provider.check("test", "database")
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.ADVISORY


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
        engine.load_policies([])
        sink = _RecordingSink()
        provider = GovernedToolProvider(engine, reg, audit_sink=sink)  # type: ignore[arg-type]
        await provider.check("test", "database")
        assert len(sink.events) == 1
        assert sink.events[0]["event"] == "policy.evaluated"
        details = sink.events[0]["details"]
        assert isinstance(details, dict)
        assert details["stage"] == "pre_tool"
