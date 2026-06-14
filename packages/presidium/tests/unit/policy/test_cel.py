from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from presidium.errors import PolicyCompilationError
from presidium.model import (
    ActionRequest,
    AgentRecord,
    AgentStatus,
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine


def _make_context(
    resource: str = "tool:database",
    action: str = "read",
    trust_value: float = 0.5,
    trust_tier: TrustTier = TrustTier.STANDARD,
    grants: list[Grant] | None = None,
    owner: str = "alice@acme.com",
    result: dict[str, Any] | None = None,
) -> EvaluationContext:
    agent = AgentRecord(
        agent_id="presidium://local/test",
        name="test",
        public_key="a2V5",
        trust_value=trust_value,
        trust_tier=trust_tier,
        grants=grants or [],
        owner=owner,
        status=AgentStatus.RUNNING,
    )
    return EvaluationContext(
        agent=agent,
        request=ActionRequest(resource=resource, action=action),
        time=datetime.now(UTC),
        result=result,
    )


ENFORCE_GRANTS = PolicyRule(
    name="enforce-grants",
    stage=[EvaluationStage.PRE_TOOL, EvaluationStage.PRE_LLM],
    expression="""
        !agent.grants.exists(g,
            request.resource in g.resources &&
            request.action in g.actions
        )
    """,
    decision=PolicyDecision.DENY,
    reason="Agent does not hold a grant for this resource/action",
    priority=100,
)

TRUST_GATE_WRITES = PolicyRule(
    name="trust-gate-writes",
    stage=EvaluationStage.PRE_TOOL,
    expression='request.action == "write" && agent.trust.value < 0.7',
    decision=PolicyDecision.REQUIRE_APPROVAL,
    reason="Write actions require approval when trust is below 0.7",
    approvers=("security@acme.com",),
    priority=90,
)

REQUIRE_OWNER = PolicyRule(
    name="require-owner",
    stage=EvaluationStage.REGISTRATION,
    expression="agent.owner == '' || agent.owner == ''",
    decision=PolicyDecision.DENY,
    reason="All agents must have an owner",
    priority=100,
    enforcement=EnforcementMode.SOFT,
)

ADVISORY_RULE = PolicyRule(
    name="restrict-expensive-models",
    stage=EvaluationStage.PRE_LLM,
    expression='request.resource == "llm:claude-opus" && agent.trust.tier != "trusted"',
    decision=PolicyDecision.DENY,
    reason="Only trusted agents can use expensive models",
    priority=70,
    enforcement=EnforcementMode.ADVISORY,
)

DISABLED_RULE = PolicyRule(
    name="disabled-rule",
    stage=EvaluationStage.PRE_TOOL,
    expression="true",
    decision=PolicyDecision.DENY,
    priority=200,
    enabled=False,
)

BAD_EXPRESSION_RULE = PolicyRule(
    name="bad-expr",
    stage=EvaluationStage.PRE_TOOL,
    expression="this is not valid CEL !!!",
    decision=PolicyDecision.DENY,
    priority=50,
)


class TestCelPolicyEngineLoadPolicies:
    def test_loads_valid_policies(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, TRUST_GATE_WRITES])

    def test_rejects_bad_expression(self) -> None:
        engine = CelPolicyEngine()
        with pytest.raises(PolicyCompilationError) as exc_info:
            engine.load_policies([BAD_EXPRESSION_RULE])
        assert exc_info.value.policy_name == "bad-expr"

    def test_skips_disabled_rules(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([DISABLED_RULE])
        assert EvaluationStage.PRE_TOOL not in engine._rules_by_stage


class TestCelPolicyEngineEvaluate:
    async def test_allow_when_no_rules(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())
        assert result.decision == PolicyDecision.ALLOW
        assert result.policy_name is None

    async def test_allow_with_matching_grant(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        ctx = _make_context(grants=[Grant(resources=["tool:database"], actions=["read"], id="g1")])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_deny_without_matching_grant(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        ctx = _make_context(grants=[])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "enforce-grants"

    async def test_require_approval_for_low_trust_write(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([TRUST_GATE_WRITES])
        ctx = _make_context(
            action="write",
            trust_value=0.5,
            grants=[Grant(resources=["tool:database"], actions=["write"], id="g1")],
        )
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.REQUIRE_APPROVAL
        assert result.approvers == ["security@acme.com"]

    async def test_allow_high_trust_write(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([TRUST_GATE_WRITES])
        ctx = _make_context(action="write", trust_value=0.8)
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_first_match_wins_by_priority(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, TRUST_GATE_WRITES])
        ctx = _make_context(action="write", trust_value=0.5, grants=[])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        # enforce-grants (priority=100) matches first — no grant for write
        assert result.policy_name == "enforce-grants"
        assert result.decision == PolicyDecision.DENY

    async def test_advisory_enforcement(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ADVISORY_RULE])
        ctx = _make_context(
            resource="llm:claude-opus",
            trust_value=0.5,
            trust_tier=TrustTier.STANDARD,
        )
        result = await engine.evaluate(EvaluationStage.PRE_LLM, ctx)
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.ADVISORY

    async def test_soft_enforcement(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([REQUIRE_OWNER])
        ctx = _make_context(owner="")
        result = await engine.evaluate(EvaluationStage.REGISTRATION, ctx)
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.SOFT


class TestCelPolicyEngineMultiStage:
    async def test_multi_stage_rule_applies_to_both(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        ctx = _make_context(grants=[])

        result_tool = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result_tool.decision == PolicyDecision.DENY

        result_llm = await engine.evaluate(EvaluationStage.PRE_LLM, ctx)
        assert result_llm.decision == PolicyDecision.DENY

    async def test_stage_without_rules_allows(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        ctx = _make_context()
        result = await engine.evaluate(EvaluationStage.REGISTRATION, ctx)
        assert result.decision == PolicyDecision.ALLOW


class TestCelPolicyEngineGrantFiltering:
    async def test_expired_grants_filtered(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        expired_grant = Grant(
            resources=["tool:database"],
            actions=["read"],
            id="expired",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        ctx = _make_context(grants=[expired_grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_active_grants_not_filtered(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        active_grant = Grant(
            resources=["tool:database"],
            actions=["read"],
            id="active",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        ctx = _make_context(grants=[active_grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_no_expiry_grant_not_filtered(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        grant = Grant(resources=["tool:database"], actions=["read"], id="nox")
        ctx = _make_context(grants=[grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW


class TestCelPolicyEngineFailClosed:
    async def test_eval_error_returns_deny(self) -> None:
        engine = CelPolicyEngine()
        rule = PolicyRule(
            name="bad-field-access",
            stage=EvaluationStage.PRE_TOOL,
            expression="agent.nonexistent_field > 0",
            decision=PolicyDecision.ALLOW,
            priority=50,
        )
        engine.load_policies([rule])
        ctx = _make_context()
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "bad-field-access"
        assert result.enforcement == EnforcementMode.HARD
        assert "fail-closed" in (result.reason or "").lower()


class TestCelPolicyEnginePostExecution:
    async def test_post_tool_evaluates_result(self) -> None:
        engine = CelPolicyEngine()
        rule = PolicyRule(
            name="block-large-results",
            stage=EvaluationStage.POST_TOOL,
            expression="result.size_bytes > 100000",
            decision=PolicyDecision.DENY,
            reason="Tool result exceeds size limit",
            priority=80,
        )
        engine.load_policies([rule])
        ctx = _make_context(result={"size_bytes": 200000, "content": "large data"})
        result = await engine.evaluate(EvaluationStage.POST_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "block-large-results"

    async def test_post_tool_allows_small_result(self) -> None:
        engine = CelPolicyEngine()
        rule = PolicyRule(
            name="block-large-results",
            stage=EvaluationStage.POST_TOOL,
            expression="result.size_bytes > 100000",
            decision=PolicyDecision.DENY,
            priority=80,
        )
        engine.load_policies([rule])
        ctx = _make_context(result={"size_bytes": 500, "content": "small"})
        result = await engine.evaluate(EvaluationStage.POST_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_post_llm_evaluates_response(self) -> None:
        engine = CelPolicyEngine()
        rule = PolicyRule(
            name="block-empty-responses",
            stage=EvaluationStage.POST_LLM,
            expression='result.content == ""',
            decision=PolicyDecision.DENY,
            reason="LLM returned empty response",
            priority=80,
        )
        engine.load_policies([rule])
        ctx = _make_context(result={"content": "", "tokens": 0})
        result = await engine.evaluate(EvaluationStage.POST_LLM, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_post_llm_allows_valid_response(self) -> None:
        engine = CelPolicyEngine()
        rule = PolicyRule(
            name="block-empty-responses",
            stage=EvaluationStage.POST_LLM,
            expression='result.content == ""',
            decision=PolicyDecision.DENY,
            priority=80,
        )
        engine.load_policies([rule])
        ctx = _make_context(result={"content": "valid response", "tokens": 50})
        result = await engine.evaluate(EvaluationStage.POST_LLM, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_result_empty_dict_for_pre_execution(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        ctx = _make_context(grants=[])
        assert ctx.result is None
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY
