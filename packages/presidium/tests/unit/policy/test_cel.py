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
from tests.policy_fixtures import ALLOW_ALL


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
    async def test_deny_when_no_rules_real_default_2026_08_24(self) -> None:
        """The real, current default -- flipped from ALLOW, see
        docs/design/policy-engine.md's "Design Decisions" P5 for the full
        reasoning. This is the actual behavior under test now, not a
        patched-to-keep-passing artifact.
        """
        engine = CelPolicyEngine()
        engine.load_policies([])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())
        assert result.decision == PolicyDecision.DENY
        assert result.policy_name is None
        assert result.enforcement == EnforcementMode.HARD
        assert "fail-closed default" in (result.reason or "")

    async def test_allow_unmatched_requests_true_restores_old_behavior(self) -> None:
        """The real, explicit, loud opt-out -- matches this codebase's own
        allow_ungoverned/allow_unsandboxed naming precedent, not a neutral
        default_decision enum."""
        engine = CelPolicyEngine(allow_unmatched_requests=True)
        engine.load_policies([])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())
        assert result.decision == PolicyDecision.ALLOW
        assert result.policy_name is None

    async def test_unmatched_enforcement_advisory_for_gradual_migration(self) -> None:
        """A migrating deployment can keep the real DENY decision (so it
        shows up in real audit logs) while running in ADVISORY mode --
        logged, not blocking -- before committing to HARD."""
        engine = CelPolicyEngine(unmatched_enforcement=EnforcementMode.ADVISORY)
        engine.load_policies([])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())
        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.ADVISORY

    async def test_allow_with_matching_grant(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
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
        engine.load_policies([TRUST_GATE_WRITES, ALLOW_ALL])
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

    async def test_stage_without_rules_denies_by_default(self) -> None:
        """Real, current behavior -- a stage with zero policies attached now
        denies, matching the flat, no-implicit-exceptions default-deny
        posture (a stage nobody bothered to write ANY policy for is not a
        special, automatically-safe case).
        """
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        ctx = _make_context()
        result = await engine.evaluate(EvaluationStage.REGISTRATION, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_stage_without_rules_allows_with_explicit_allow_all(self) -> None:
        """The real migration story for the case above: a deployment that
        genuinely wants an unrestricted stage adds an explicit ALLOW rule
        for it -- not silently relying on "nobody wrote a policy" meaning
        safe."""
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
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
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
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
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
        grant = Grant(resources=["tool:database"], actions=["read"], id="nox")
        ctx = _make_context(grants=[grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW


class TestGrantConditionRealEvaluation:
    """Grant.condition (2026-08-25 fix) -- was previously a documented-but-dead
    field: serialized/deserialized, injected into the activation as an inert
    string, never compiled or executed. These prove it's real now."""

    async def test_true_condition_keeps_grant_active(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
        grant = Grant(
            resources=["tool:database"],
            actions=["read"],
            id="conditional",
            condition="agent.trust.value >= 0.4",
        )
        ctx = _make_context(grants=[grant], trust_value=0.5)
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_false_condition_excludes_grant(self) -> None:
        """The load-bearing case the original report described: a grant whose
        condition isn't met must NOT unconditionally authorize the request."""
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        grant = Grant(
            resources=["tool:database"],
            actions=["read"],
            id="conditional",
            condition="agent.trust.value >= 0.9",
        )
        ctx = _make_context(grants=[grant], trust_value=0.5)
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_condition_can_reference_request(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        grant = Grant(
            resources=["tool:database"],
            actions=["read", "write"],
            id="conditional",
            condition='request.action != "write"',
        )
        ctx = _make_context(grants=[grant], action="write")
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_none_condition_always_active(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
        grant = Grant(resources=["tool:database"], actions=["read"], id="unconditional")
        ctx = _make_context(grants=[grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_empty_string_condition_always_active(self) -> None:
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
        grant = Grant(
            resources=["tool:database"], actions=["read"], id="unconditional", condition=""
        )
        ctx = _make_context(grants=[grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_uncompilable_condition_fails_closed_not_a_crash(self) -> None:
        """A syntactically invalid condition must not silently pass (the original
        bug) nor blow up the whole evaluation -- the grant is simply inactive."""
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        grant = Grant(
            resources=["tool:database"],
            actions=["read"],
            id="broken",
            condition="this is not valid CEL !!!",
        )
        ctx = _make_context(grants=[grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_condition_referencing_unknown_field_fails_closed(self) -> None:
        """Compiles fine, raises at evaluation time (unknown field access) --
        must also fail closed, not propagate an exception out of evaluate()."""
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        grant = Grant(
            resources=["tool:database"],
            actions=["read"],
            id="broken",
            condition="agent.nonexistent_field > 0",
        )
        ctx = _make_context(grants=[grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_condition_compiled_once_cached_across_evaluations(self) -> None:
        """Same expression text across two different grants/requests should hit
        the compile cache, not recompile -- observable via the cache dict itself."""
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS, ALLOW_ALL])
        condition = "agent.trust.value >= 0.4"
        grant = Grant(resources=["tool:database"], actions=["read"], id="a", condition=condition)
        ctx = _make_context(grants=[grant], trust_value=0.5)
        await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert condition in engine._condition_programs
        cached_program = engine._condition_programs[condition]

        grant2 = Grant(resources=["tool:database"], actions=["read"], id="b", condition=condition)
        ctx2 = _make_context(grants=[grant2], trust_value=0.5)
        await engine.evaluate(EvaluationStage.PRE_TOOL, ctx2)
        assert engine._condition_programs[condition] is cached_program

    async def test_condition_cannot_see_agent_grants(self) -> None:
        """Deliberately excluded from the condition's own activation -- a grant
        deciding its own activity from its own list membership would be
        self-referential and ill-defined."""
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        grant = Grant(
            resources=["tool:database"],
            actions=["read"],
            id="broken",
            condition="agent.grants.size() > 0",
        )
        ctx = _make_context(grants=[grant])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY


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
        engine.load_policies([rule, ALLOW_ALL])
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
        engine.load_policies([rule, ALLOW_ALL])
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


class TestPreMessageStage:
    async def test_pre_message_stage_exists(self) -> None:
        assert EvaluationStage.PRE_MESSAGE.value == "pre_message"

    async def test_pre_message_policies_evaluated(self) -> None:
        rule = PolicyRule(
            name="block-untrusted-messages",
            stage=EvaluationStage.PRE_MESSAGE,
            expression='agent.trust.tier == "restricted"',
            decision=PolicyDecision.DENY,
            reason="Restricted agents cannot send messages",
            priority=90,
        )
        engine = CelPolicyEngine()
        engine.load_policies([rule])
        ctx = _make_context(
            resource="message:task",
            action="send",
            trust_value=0.1,
            trust_tier=TrustTier.RESTRICTED,
        )
        result = await engine.evaluate(EvaluationStage.PRE_MESSAGE, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_pre_message_allow_trusted(self) -> None:
        rule = PolicyRule(
            name="block-untrusted-messages",
            stage=EvaluationStage.PRE_MESSAGE,
            expression='agent.trust.tier == "restricted"',
            decision=PolicyDecision.DENY,
            reason="Restricted agents cannot send messages",
            priority=90,
        )
        engine = CelPolicyEngine()
        engine.load_policies([rule, ALLOW_ALL])
        ctx = _make_context(
            resource="message:task",
            action="send",
            trust_value=0.8,
            trust_tier=TrustTier.TRUSTED,
        )
        result = await engine.evaluate(EvaluationStage.PRE_MESSAGE, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_pre_message_in_multi_stage_rule(self) -> None:
        rule = PolicyRule(
            name="universal-grant-check",
            stage=[EvaluationStage.PRE_TOOL, EvaluationStage.PRE_LLM, EvaluationStage.PRE_MESSAGE],
            expression="agent.grants.size() == 0",
            decision=PolicyDecision.DENY,
            reason="No grants",
            priority=100,
        )
        engine = CelPolicyEngine()
        engine.load_policies([rule])
        ctx = _make_context(grants=[])
        result = await engine.evaluate(EvaluationStage.PRE_MESSAGE, ctx)
        assert result.decision == PolicyDecision.DENY


class TestPolicyHotReload:
    async def test_load_replaces_previous_rules(self) -> None:
        engine = CelPolicyEngine()
        rule1 = PolicyRule(
            name="block-all",
            stage=EvaluationStage.PRE_TOOL,
            expression="true",
            decision=PolicyDecision.DENY,
            reason="Blocked",
            priority=100,
        )
        engine.load_policies([rule1])
        ctx = _make_context()
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY

        rule2 = PolicyRule(
            name="allow-all-explicit",
            stage=EvaluationStage.PRE_TOOL,
            expression="true",
            decision=PolicyDecision.ALLOW,
            reason="Explicit allow -- real, unambiguous proof reload replaced rule1's own"
            " always-DENY, not just fell through to it not matching. (Previously this test"
            " used expression='false', an always-false rule that only proved this via the"
            " old implicit-ALLOW fallback -- an accidental dependency on the very default"
            " this file no longer has, not a real test of replacement.)",
            priority=100,
        )
        engine.load_policies([rule2])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_reload_clears_old_stages(self) -> None:
        engine = CelPolicyEngine()
        rule_tool = PolicyRule(
            name="tool-block",
            stage=EvaluationStage.PRE_TOOL,
            expression="true",
            decision=PolicyDecision.DENY,
            reason="Blocked",
            priority=100,
        )
        rule_llm = PolicyRule(
            name="llm-block",
            stage=EvaluationStage.PRE_LLM,
            expression="true",
            decision=PolicyDecision.DENY,
            reason="Blocked",
            priority=100,
        )
        engine.load_policies([rule_tool, rule_llm])

        # Real, unambiguous proof rule_llm was actually cleared, not just
        # "happened not to match": include an explicit ALLOW for PRE_LLM in
        # the reload, then confirm PRE_LLM now allows -- if rule_llm (DENY,
        # priority 100) were still active, its higher priority would still
        # win and this would still deny.
        engine.load_policies([rule_tool, ALLOW_ALL])
        ctx = _make_context()
        result = await engine.evaluate(EvaluationStage.PRE_LLM, ctx)
        assert result.decision == PolicyDecision.ALLOW

    async def test_reload_to_a_stage_with_no_new_rules_denies_by_default(self) -> None:
        """Real, current behavior -- reloading with a rule set that no
        longer covers a given stage now denies that stage by default,
        matching test_stage_without_rules_denies_by_default's own real
        finding, not a special case for reload specifically.
        """
        engine = CelPolicyEngine()
        rule_tool = PolicyRule(
            name="tool-block",
            stage=EvaluationStage.PRE_TOOL,
            expression="true",
            decision=PolicyDecision.DENY,
            reason="Blocked",
            priority=100,
        )
        rule_llm = PolicyRule(
            name="llm-block",
            stage=EvaluationStage.PRE_LLM,
            expression="true",
            decision=PolicyDecision.DENY,
            reason="Blocked",
            priority=100,
        )
        engine.load_policies([rule_tool, rule_llm])
        engine.load_policies([rule_tool])
        ctx = _make_context()
        result = await engine.evaluate(EvaluationStage.PRE_LLM, ctx)
        assert result.decision == PolicyDecision.DENY

    async def test_empty_reload_denies_by_default(self) -> None:
        """Real, current behavior -- reloading with zero rules leaves the
        engine with nothing to evaluate, so the real default-deny fallback
        applies, same as if the engine had never had any policies at all.
        """
        engine = CelPolicyEngine()
        engine.load_policies([ENFORCE_GRANTS])
        engine.load_policies([])
        ctx = _make_context(grants=[])
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, ctx)
        assert result.decision == PolicyDecision.DENY
