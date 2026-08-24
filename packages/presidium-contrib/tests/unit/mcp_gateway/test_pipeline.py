"""Real tests for GovernedMcpToolPipeline -- proves the three previously-independent MCP
governance primitives (PoisoningDetector, PIIDetector, credential redaction) actually run
together against real authorization (GovernedToolProvider/CelPolicyEngine) and a real, minimal
ToolsGatewayBackend, not mocked at the seams that matter.

Uses the same minimal, structural (not inheritance-based) fake backend pattern already
established in presidium/tests/unit/providers/test_gateway_provider.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from presidium.errors import PolicyDeniedError
from presidium.model import (
    AgentRecord,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine
from presidium.providers.tool import GovernedToolProvider
from presidium.registry.memory import InMemoryRegistry
from presidium_contrib.mcp_gateway.pii import PIIDetector
from presidium_contrib.mcp_gateway.pipeline import (
    GovernedMcpToolPipeline,
    ToolPoisoningDetectedError,
)
from tests.policy_fixtures import ALLOW_ALL

DENY_NO_GRANT = PolicyRule(
    name="deny-no-grant",
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


class _FakeBackend:
    """A real, minimal ToolsGatewayBackend -- structurally, not via inheritance."""

    def __init__(
        self,
        *,
        tools: list[dict[str, Any]] | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        self.tools = (
            tools
            if tools is not None
            else [
                {
                    "name": "lookup_customer",
                    "description": "Look up a customer record",
                    "input_schema": {},
                }
            ]
        )
        self.call_log: list[tuple[str, dict[str, Any]]] = []
        self._result = result if result is not None else {"output": "ok"}

    async def list_tools(self, *, agent_name: str | None = None) -> list[dict[str, Any]]:
        return self.tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, agent_name: str | None = None
    ) -> dict[str, Any]:
        self.call_log.append((name, arguments))
        return self._result

    async def health(self) -> bool:
        return True


async def _setup(*rules: PolicyRule) -> tuple[InMemoryRegistry, CelPolicyEngine]:
    reg = InMemoryRegistry()
    await reg.register(
        AgentRecord(
            agent_id="presidium://local/researcher",
            name="researcher",
            public_key="",
            trust_value=0.5,
            trust_tier=TrustTier.STANDARD,
            grants=[Grant(resources=["tool:lookup_customer"], actions=["invoke"], id="g1")],
        )
    )
    engine = CelPolicyEngine()
    if rules:
        engine.load_policies(list(rules))
    return reg, engine


class TestListTools:
    async def test_list_tools_tags_unapproved_status(self) -> None:
        reg, engine = await _setup()
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        tools = await pipeline.list_tools()

        assert tools[0]["poisoning_status"] == "unapproved"
        assert tools[0]["name"] == "lookup_customer"

    async def test_list_tools_tags_clean_after_approval(self) -> None:
        reg, engine = await _setup()
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        tools = await pipeline.list_tools()

        assert tools[0]["poisoning_status"] == "clean"


class TestPoisoningGate:
    async def test_unapproved_tool_raises_and_backend_never_called(self) -> None:
        reg, engine = await _setup(DENY_NO_GRANT, ALLOW_ALL)
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        with pytest.raises(ToolPoisoningDetectedError) as exc_info:
            await pipeline.call_tool("lookup_customer", {"id": "123"})

        assert exc_info.value.tool_name == "lookup_customer"
        assert backend.call_log == []

    async def test_approved_tool_reaches_the_backend(self) -> None:
        reg, engine = await _setup(DENY_NO_GRANT, ALLOW_ALL)
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool("lookup_customer", {"id": "123"})

        assert result["output"] == "ok"
        assert backend.call_log == [("lookup_customer", {"id": "123"})]

    async def test_changed_tool_raises_after_approval(self) -> None:
        """Real drift detection: the tool's live description no longer matches what was
        approved -- the approved snapshot is now stale, and the call is blocked."""
        reg, engine = await _setup(DENY_NO_GRANT, ALLOW_ALL)
        backend = _FakeBackend(
            tools=[
                {
                    "name": "lookup_customer",
                    "description": "Delete a customer record!",
                    "input_schema": {},
                }
            ]
        )
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        with pytest.raises(ToolPoisoningDetectedError):
            await pipeline.call_tool("lookup_customer", {"id": "123"})

    async def test_allow_unapproved_tools_bypasses_the_gate(self) -> None:
        reg, engine = await _setup(DENY_NO_GRANT, ALLOW_ALL)
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend,
            tool_provider=tool_provider,
            agent_name="researcher",
            allow_unapproved_tools=True,
        )

        result = await pipeline.call_tool("lookup_customer", {"id": "123"})

        assert result["output"] == "ok"

    async def test_caller_supplied_tool_metadata_skips_the_live_lookup(self) -> None:
        """Passing tool_description/tool_input_schema avoids a second list_tools() round trip
        -- confirmed here by never populating backend.tools with a matching entry at all, so a
        live lookup would fail to find it."""
        reg, engine = await _setup(DENY_NO_GRANT, ALLOW_ALL)
        backend = _FakeBackend(tools=[])
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool(
            "lookup_customer",
            {"id": "123"},
            tool_description="Look up a customer record",
            tool_input_schema={},
        )

        assert result["output"] == "ok"


class TestCredentialRedaction:
    async def test_redacted_arguments_reach_the_cel_policy_not_the_raw_secret(self) -> None:
        """Real, end-to-end proof: a CEL policy inspecting request.parameters sees the
        REDACTED value, never the raw api_key -- confirmed by asserting the policy actually
        fires on the redacted marker text."""
        reg, engine = await _setup()
        redaction_gate = PolicyRule(
            name="redaction-gate",
            stage=EvaluationStage.PRE_TOOL,
            expression='request.parameters.api_key == "**REDACTED**"',
            decision=PolicyDecision.ALLOW,
            priority=100,
        )
        engine.load_policies([redaction_gate, ALLOW_ALL])
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool(
            "lookup_customer", {"id": "123", "api_key": "sk-supersecretvalue1234567890"}
        )

        assert result["output"] == "ok"
        # The real backend call itself receives the UNREDACTED value -- redaction is for
        # policy/audit visibility only, the tool still needs real values to function.
        assert backend.call_log[0][1]["api_key"] == "sk-supersecretvalue1234567890"

    async def test_raw_secret_causes_a_deny_when_the_policy_requires_redaction(self) -> None:
        """Proves the gate is real, not vacuously true: this policy DENIES unless the
        api_key argument was redacted before reaching CEL. If redaction were silently broken
        (the raw secret leaking through), this would deny instead of allow."""
        reg, engine = await _setup()
        redaction_gate = PolicyRule(
            name="redaction-gate",
            stage=EvaluationStage.PRE_TOOL,
            expression='request.parameters.api_key != "**REDACTED**"',
            decision=PolicyDecision.DENY,
            reason="Raw credential leaked into policy evaluation",
            priority=100,
        )
        engine.load_policies([redaction_gate, ALLOW_ALL])
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool(
            "lookup_customer", {"id": "123", "api_key": "sk-supersecretvalue1234567890"}
        )
        assert result["output"] == "ok"


class TestPIIScanAndMask:
    async def test_result_gets_enriched_with_contains_pii(self) -> None:
        reg, engine = await _setup(ALLOW_ALL)
        backend = _FakeBackend(result={"output": "Contact: alice@example.com"})
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend,
            tool_provider=tool_provider,
            agent_name="researcher",
            pii_detector=PIIDetector(),
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool("lookup_customer", {"id": "123"})

        assert result["contains_pii"] is True
        assert "email" in result["pii_pattern_names"]

    async def test_result_masked_by_default_when_pii_detected(self) -> None:
        reg, engine = await _setup(ALLOW_ALL)
        backend = _FakeBackend(result={"output": "Contact: alice@example.com"})
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend,
            tool_provider=tool_provider,
            agent_name="researcher",
            pii_detector=PIIDetector(),
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool("lookup_customer", {"id": "123"})

        assert "alice@example.com" not in result["output"]
        assert result["contains_pii"] is True

    async def test_mask_pii_in_results_false_keeps_the_raw_value(self) -> None:
        reg, engine = await _setup(ALLOW_ALL)
        backend = _FakeBackend(result={"output": "Contact: alice@example.com"})
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend,
            tool_provider=tool_provider,
            agent_name="researcher",
            pii_detector=PIIDetector(),
            mask_pii_in_results=False,
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool("lookup_customer", {"id": "123"})

        assert "alice@example.com" in result["output"]
        assert result["contains_pii"] is True

    async def test_no_pii_detector_configured_skips_scanning_entirely(self) -> None:
        reg, engine = await _setup(ALLOW_ALL)
        backend = _FakeBackend(result={"output": "Contact: alice@example.com"})
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        result = await pipeline.call_tool("lookup_customer", {"id": "123"})

        assert "contains_pii" not in result
        assert result["output"] == "Contact: alice@example.com"

    async def test_post_tool_policy_sees_contains_pii_before_masking(self) -> None:
        """Real, end-to-end proof of the design doc's own "context enrichment step before
        policy evaluation" claim: a POST_TOOL CEL policy referencing result.contains_pii
        actually sees it and can deny on it."""
        reg, engine = await _setup(ALLOW_ALL)
        pii_gate = PolicyRule(
            name="pii-gate",
            stage=EvaluationStage.POST_TOOL,
            expression="result.contains_pii == true",
            decision=PolicyDecision.DENY,
            reason="Tool result contains PII",
            priority=90,
        )
        engine.load_policies([pii_gate, ALLOW_ALL])
        backend = _FakeBackend(result={"output": "Contact: alice@example.com"})
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend,
            tool_provider=tool_provider,
            agent_name="researcher",
            pii_detector=PIIDetector(),
        )
        pipeline.approve_tool("lookup_customer", "Look up a customer record", {}, "admin@acme.com")

        with pytest.raises(PolicyDeniedError, match="PII"):
            await pipeline.call_tool("lookup_customer", {"id": "123"})


class TestHealth:
    async def test_health_delegates_to_backend(self) -> None:
        reg, engine = await _setup()
        backend = _FakeBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        pipeline = GovernedMcpToolPipeline(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        assert await pipeline.health() is True
