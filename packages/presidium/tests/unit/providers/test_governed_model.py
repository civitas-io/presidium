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
from presidium.providers.model import GovernedModelProvider
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
            grants=[Grant(resources=["llm:claude-sonnet"], actions=["invoke"], id="g1")],
            owner="alice@acme.com",
            status=AgentStatus.RUNNING,
        )
    )
    engine = CelPolicyEngine()
    return reg, engine


DENY_NO_GRANT = PolicyRule(
    name="enforce-grants",
    stage=EvaluationStage.PRE_LLM,
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

REQUIRE_APPROVAL_RULE = PolicyRule(
    name="approval-gate",
    stage=EvaluationStage.PRE_LLM,
    expression="true",
    decision=PolicyDecision.REQUIRE_APPROVAL,
    reason="All LLM calls need approval",
    approvers=("admin@acme.com",),
    priority=50,
)

ADVISORY_DENY = PolicyRule(
    name="advisory-deny",
    stage=EvaluationStage.PRE_LLM,
    expression="true",
    decision=PolicyDecision.DENY,
    reason="Testing advisory mode",
    priority=50,
    enforcement=EnforcementMode.ADVISORY,
)

SOFT_DENY = PolicyRule(
    name="soft-deny",
    stage=EvaluationStage.PRE_LLM,
    expression="true",
    decision=PolicyDecision.DENY,
    reason="Testing soft mode",
    priority=50,
    enforcement=EnforcementMode.SOFT,
)


class TestGovernedModelProviderAllow:
    async def test_allow_with_matching_grant(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT])
        provider = GovernedModelProvider(engine, reg)
        result = await provider.check("test", "claude-sonnet")
        assert result.decision == PolicyDecision.ALLOW

    async def test_allow_when_no_rules(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedModelProvider(engine, reg)
        result = await provider.check("test", "claude-sonnet")
        assert result.decision == PolicyDecision.ALLOW


class TestGovernedModelProviderDeny:
    async def test_deny_without_grant(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([DENY_NO_GRANT])
        provider = GovernedModelProvider(engine, reg)
        with pytest.raises(PolicyDeniedError) as exc_info:
            await provider.check("test", "gpt-4o")
        assert exc_info.value.policy_name == "enforce-grants"

    async def test_deny_nonexistent_agent(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedModelProvider(engine, reg)
        with pytest.raises(PolicyDeniedError):
            await provider.check("ghost", "claude-sonnet")


class TestGovernedModelProviderApproval:
    async def test_require_approval_auto_approve(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([REQUIRE_APPROVAL_RULE])
        approval = CallbackApprovalProvider(auto_approve=True)
        provider = GovernedModelProvider(engine, reg, approval=approval)
        result = await provider.check("test", "claude-sonnet")
        assert result.decision == PolicyDecision.REQUIRE_APPROVAL

    async def test_require_approval_denied(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([REQUIRE_APPROVAL_RULE])
        approval = CallbackApprovalProvider(auto_deny=True)
        provider = GovernedModelProvider(engine, reg, approval=approval)
        with pytest.raises(PolicyDeniedError, match="Approval denied"):
            await provider.check("test", "claude-sonnet")

    async def test_require_approval_no_service_raises(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([REQUIRE_APPROVAL_RULE])
        provider = GovernedModelProvider(engine, reg)
        with pytest.raises(PolicyDeniedError, match="no ApprovalService"):
            await provider.check("test", "claude-sonnet")


class TestGovernedModelProviderEnforcementModes:
    async def test_advisory_does_not_block(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([ADVISORY_DENY])
        provider = GovernedModelProvider(engine, reg)
        result = await provider.check("test", "claude-sonnet")
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.ADVISORY

    async def test_soft_does_not_block(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([SOFT_DENY])
        provider = GovernedModelProvider(engine, reg)
        result = await provider.check("test", "claude-sonnet")
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.SOFT


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def emit(self, event: dict[str, object]) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        pass


class TestGovernedModelProviderAudit:
    async def test_emits_audit_event(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        sink = _RecordingSink()
        provider = GovernedModelProvider(engine, reg, audit_sink=sink)  # type: ignore[arg-type]
        await provider.check("test", "claude-sonnet")
        assert len(sink.events) == 1
        assert sink.events[0]["event"] == "policy.evaluated"
        details = sink.events[0]["details"]
        assert isinstance(details, dict)
        assert details["stage"] == "pre_llm"


BLOCK_EMPTY_RESPONSE = PolicyRule(
    name="block-empty-response",
    stage=EvaluationStage.POST_LLM,
    expression='result.content == ""',
    decision=PolicyDecision.DENY,
    reason="LLM returned empty response",
    priority=80,
)


class TestGovernedModelProviderPostCheck:
    async def test_post_check_allows_valid_response(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([BLOCK_EMPTY_RESPONSE])
        provider = GovernedModelProvider(engine, reg)
        result = await provider.post_check(
            "test", "claude-sonnet", {"content": "hello", "tokens": 5}
        )
        assert result.decision == PolicyDecision.ALLOW

    async def test_post_check_denies_empty_response(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([BLOCK_EMPTY_RESPONSE])
        provider = GovernedModelProvider(engine, reg)
        with pytest.raises(PolicyDeniedError, match="empty response"):
            await provider.post_check("test", "claude-sonnet", {"content": "", "tokens": 0})

    async def test_post_check_nonexistent_agent_raises(self) -> None:
        reg, engine = await _setup()
        engine.load_policies([])
        provider = GovernedModelProvider(engine, reg)
        with pytest.raises(PolicyDeniedError):
            await provider.post_check("ghost", "claude-sonnet", {})
