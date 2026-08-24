"""Real tests for PresidiumGatewayAgent/HealthCheckAgent — direct handle_call() invocation.

See tests/integration/test_presidium_server_real_gateway.py for the real
end-to-end test through an actual civitas.gateway.HTTPGateway.
"""

from __future__ import annotations

from presidium.model import (
    AgentRecord,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
)
from presidium.policy.cel import CelPolicyEngine
from presidium.registry.memory import InMemoryRegistry
from presidium.runtime import GovernedRuntime
from presidium_contrib.server import HealthCheckAgent, PresidiumGatewayAgent
from tests.policy_fixtures import ALLOW_ALL

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
    expression='request.resource == "sensitive_action" && agent.trust.value < 0.7',
    decision=PolicyDecision.REQUIRE_APPROVAL,
    reason="Low trust",
    approvers=("security@acme.com",),
    priority=90,
)


async def _make_runtime(*rules: PolicyRule) -> GovernedRuntime:
    registry = InMemoryRegistry()
    await registry.register(
        AgentRecord(
            agent_id="presidium://acme.com/researcher",
            name="researcher",
            public_key="",
            grants=[Grant(resources=["code_mode"], actions=["invoke"], id="g1")],
        )
    )
    engine = CelPolicyEngine()
    if rules:
        engine.load_policies(list(rules))
    return GovernedRuntime(registry=registry, engine=engine)


class TestHealthCheckAgent:
    async def test_health_returns_ok(self) -> None:
        agent = HealthCheckAgent()
        result = await agent.handle_call({}, "sender")
        assert result == {"status": "ok"}

    async def test_health_ignores_payload_contents(self) -> None:
        """A real, minimal agent -- no dispatch-by-payload-marker logic to
        get wrong, on purpose (see gateway_agent.py's own module docstring
        for why this is a separate agent, not a second op on
        PresidiumGatewayAgent)."""
        agent = HealthCheckAgent()
        result = await agent.handle_call({"anything": "at all"}, "sender")
        assert result == {"status": "ok"}


class TestCheckGrant:
    async def test_allow_with_matching_grant(self) -> None:
        runtime = await _make_runtime(DENY_NO_GRANT, ALLOW_ALL)
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call(
            {"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
            "sender",
        )
        # Not asserting an exact reason string -- it now comes from the real
        # explicit terminal ALLOW rule this test loads (ALLOW_ALL), not the
        # engine's own old "All policies passed" no-match fallback text.
        assert result["decision"] == "allow"
        assert result["approval_context"] is None

    async def test_deny_without_matching_grant(self) -> None:
        runtime = await _make_runtime(DENY_NO_GRANT)
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "action": "skill_run:pdf-extract",
            },
            "sender",
        )
        assert result["decision"] == "deny"
        assert result["reason"] == "No matching grant"
        assert result["approval_context"] is None

    async def test_require_approval_returned_immediately(self) -> None:
        """The whole point of check_grant() over check(): this must return
        require_approval as a value, never block, even with no
        ApprovalService anywhere in the picture.
        """
        runtime = await _make_runtime(TRUST_GATE)
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call(
            {"agent_id": "presidium://acme.com/researcher", "action": "sensitive_action"},
            "sender",
        )
        assert result["decision"] == "require_approval"
        assert result["approval_context"] == {
            "policy_name": "trust-gate",
            "reason": "Low trust",
            "approvers": ["security@acme.com"],
        }

    async def test_unresolvable_agent_id_denies_not_raises(self) -> None:
        runtime = await _make_runtime()
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call(
            {"agent_id": "presidium://acme.com/ghost", "action": "code_mode"}, "sender"
        )
        assert result == {
            "decision": "deny",
            "reason": "Agent not found in registry",
            "approval_context": None,
        }

    async def test_missing_agent_id_denies_not_raises(self) -> None:
        runtime = await _make_runtime()
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call({"action": "code_mode"}, "sender")
        assert result["decision"] == "deny"
        assert "required" in result["reason"]

    async def test_missing_action_denies_not_raises(self) -> None:
        runtime = await _make_runtime()
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call({"agent_id": "presidium://acme.com/researcher"}, "sender")
        assert result["decision"] == "deny"
        assert "required" in result["reason"]

    async def test_empty_payload_denies_not_raises(self) -> None:
        runtime = await _make_runtime()
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call({}, "sender")
        assert result["decision"] == "deny"

    async def test_resource_mapping_is_verbatim_not_split(self) -> None:
        """FR-1.3 ('Option 2, refined'): a colon-bearing action string is
        NOT split/transformed -- the whole string becomes the resource.
        """
        runtime = await _make_runtime(
            PolicyRule(
                name="skill-run-allow",
                stage=EvaluationStage.PRE_TOOL,
                expression='request.resource == "skill_run:pdf-extract"',
                decision=PolicyDecision.ALLOW,
                priority=100,
            )
        )
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "action": "skill_run:pdf-extract",
            },
            "sender",
        )
        assert result["decision"] == "allow"

    async def test_scope_field_reaches_the_cel_policy_as_request_parameters(self) -> None:
        """FR-1.4, real, closes a gap this handler previously had: `scope` in the request
        body must actually reach `ActionRequest.parameters`, not be silently discarded.
        Confirmed here through the whole real stack (handle_call -> check_grant ->
        ActionRequest -> CEL evaluate), not just at the GovernedToolProvider unit level.
        """
        runtime = await _make_runtime(
            PolicyRule(
                name="tenant-gate",
                stage=EvaluationStage.PRE_TOOL,
                expression='request.parameters.tenant_id != "acme"',
                decision=PolicyDecision.DENY,
                reason="Wrong tenant",
                priority=100,
            ),
            ALLOW_ALL,
        )
        agent = PresidiumGatewayAgent(runtime=runtime)

        allowed = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "action": "code_mode",
                "scope": {"tenant_id": "acme"},
            },
            "sender",
        )
        assert allowed["decision"] == "allow"

        denied = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "action": "code_mode",
                "scope": {"tenant_id": "other-corp"},
            },
            "sender",
        )
        assert denied["decision"] == "deny"
        assert denied["reason"] == "Wrong tenant"

    async def test_scope_omitted_is_not_an_error(self) -> None:
        """A request with no `scope` field at all (most real callers, most of the time) must
        keep working exactly as before -- `scope` is additive, not a new requirement.
        """
        runtime = await _make_runtime(DENY_NO_GRANT, ALLOW_ALL)
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call(
            {"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
            "sender",
        )
        assert result["decision"] == "allow"

    async def test_scope_wrong_type_denies_not_raises(self) -> None:
        """Fail-closed on a malformed `scope` (e.g. a list or a string instead of an object),
        matching this whole handler's own established "never raise, always deny" contract for
        every other malformed-input case."""
        runtime = await _make_runtime(DENY_NO_GRANT, ALLOW_ALL)
        agent = PresidiumGatewayAgent(runtime=runtime)
        result = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "action": "code_mode",
                "scope": ["not", "an", "object"],
            },
            "sender",
        )
        assert result["decision"] == "deny"
        assert "scope" in result["reason"]
