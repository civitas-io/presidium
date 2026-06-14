from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from presidium.model import (
    ActionRequest,
    AgentRecord,
    AgentStatus,
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    Grant,
    PolicyDecision,
    TrustTier,
)
from presidium_contrib.opa.engine import OPAPolicyEngine


def _make_context(
    resource: str = "tool:database",
    action: str = "read",
) -> EvaluationContext:
    return EvaluationContext(
        agent=AgentRecord(
            agent_id="presidium://local/test",
            name="test",
            public_key="a2V5",
            trust_value=0.5,
            trust_tier=TrustTier.STANDARD,
            grants=[Grant(resources=["tool:database"], actions=["read"], id="g1")],
            owner="alice@acme.com",
            status=AgentStatus.RUNNING,
        ),
        request=ActionRequest(resource=resource, action=action),
        time=datetime.now(UTC),
    )


def _mock_opa_response(result: dict[str, object]) -> AsyncMock:
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {"result": result}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestOPAPolicyEngineEvaluate:
    async def test_allow_decision(self) -> None:
        mock_client = _mock_opa_response({"decision": "allow", "reason": "all good"})

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.ALLOW
        assert result.reason == "all good"

    async def test_deny_decision(self) -> None:
        mock_client = _mock_opa_response(
            {
                "decision": "deny",
                "reason": "no grant",
                "policy_name": "enforce-grants",
            }
        )

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "enforce-grants"

    async def test_require_approval_with_approvers(self) -> None:
        mock_client = _mock_opa_response(
            {
                "decision": "require_approval",
                "reason": "needs sign-off",
                "approvers": ["admin@acme.com"],
            }
        )

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.REQUIRE_APPROVAL
        assert result.approvers == ["admin@acme.com"]

    async def test_advisory_enforcement(self) -> None:
        mock_client = _mock_opa_response(
            {
                "decision": "deny",
                "enforcement": "advisory",
            }
        )

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.ADVISORY

    async def test_empty_result_defaults_to_allow(self) -> None:
        mock_client = _mock_opa_response({})

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.ALLOW


class TestOPAPolicyEngineFailClosed:
    async def test_connection_error_returns_deny(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.DENY
        assert result.enforcement == EnforcementMode.HARD
        assert "fail-closed" in (result.reason or "").lower()


class TestOPAPolicyEngineRequest:
    async def test_sends_correct_url_for_stage(self) -> None:
        mock_client = _mock_opa_response({"decision": "allow"})

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            await engine.evaluate(EvaluationStage.POST_LLM, _make_context())

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:8181/v1/data/presidium/post_llm"

    async def test_sends_agent_context_as_input(self) -> None:
        mock_client = _mock_opa_response({"decision": "allow"})

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        call_kwargs = mock_client.post.call_args[1]
        body = call_kwargs["json"]
        assert body["input"]["agent"]["name"] == "test"
        assert body["input"]["request"]["resource"] == "tool:database"

    async def test_custom_headers_sent(self) -> None:
        mock_client = _mock_opa_response({"decision": "allow"})

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine(
                "http://localhost:8181",
                headers={"Authorization": "Bearer tok"},
            )
            await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer tok"


class TestOPAPolicyEngineInvalidValues:
    async def test_invalid_decision_defaults_to_deny(self) -> None:
        mock_client = _mock_opa_response({"decision": "bogus_value"})

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.DENY

    async def test_invalid_enforcement_defaults_to_hard(self) -> None:
        mock_client = _mock_opa_response({
            "decision": "allow",
            "enforcement": "bogus_mode",
        })

        with patch("presidium_contrib.opa.engine.httpx.AsyncClient", return_value=mock_client):
            engine = OPAPolicyEngine("http://localhost:8181")
            result = await engine.evaluate(EvaluationStage.PRE_TOOL, _make_context())

        assert result.decision == PolicyDecision.ALLOW
        assert result.enforcement == EnforcementMode.HARD


class TestOPAPolicyEngineLoadPolicies:
    def test_load_policies_is_noop(self) -> None:
        engine = OPAPolicyEngine()
        engine.load_policies([])
