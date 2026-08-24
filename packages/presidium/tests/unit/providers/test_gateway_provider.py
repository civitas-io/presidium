"""Real tests for GatewayModelProvider/GatewayToolProvider.

Uses minimal, real (not mocked) fake backends that structurally satisfy
LLMGatewayBackend/ToolsGatewayBackend -- mirrors test_civitas_adapters.py's
own established pattern exactly, applied to the gateway-backend integration
point instead of the direct-civitas-provider one. See
docs/design/mcp-gateway.md's "Design decisions, 2026-08-24" for the full
reasoning this test suite verifies.
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
from presidium.providers.gateway import GatewayModelProvider, GatewayToolProvider
from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider
from presidium.registry.memory import InMemoryRegistry
from tests.policy_fixtures import ALLOW_ALL


class _FakeLLMGatewayBackend:
    """A real, minimal LLMGatewayBackend -- structurally, not via inheritance."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[list[dict[str, str]], str | None]] = []
        self._response = response or {"content": "hello", "tokens_out": 5}

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append((messages, model))
        return self._response

    async def list_models(self) -> list[dict[str, Any]]:
        return [{"id": "claude-sonnet"}, {"id": "gpt-4"}]

    async def health(self) -> bool:
        return True


class _FakeToolsGatewayBackend:
    """A real, minimal ToolsGatewayBackend."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.delegate_calls: list[tuple[str, dict[str, Any]]] = []
        self._result = result if result is not None else {"output": "ok"}

    async def list_tools(self, *, agent_name: str | None = None) -> list[dict[str, Any]]:
        return [{"name": "database"}, {"name": "web_search"}]

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, agent_name: str | None = None
    ) -> dict[str, Any]:
        self.tool_calls.append((name, arguments))
        return self._result

    async def delegate_to_agent(
        self, agent_name_target: str, arguments: dict[str, Any], *, agent_name: str | None = None
    ) -> dict[str, Any]:
        self.delegate_calls.append((agent_name_target, arguments))
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
            grants=[
                Grant(resources=["tool:web_search"], actions=["invoke"], id="g1"),
                Grant(resources=["agent:specialist_researcher"], actions=["invoke"], id="g2"),
                Grant(resources=["llm:claude-sonnet"], actions=["invoke"], id="g3"),
            ],
        )
    )
    engine = CelPolicyEngine()
    if rules:
        engine.load_policies(list(rules))
    return reg, engine


DENY_NO_GRANT_TOOL = PolicyRule(
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

DENY_NO_GRANT_LLM = PolicyRule(
    name="deny-no-grant-llm",
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


class TestGatewayModelProvider:
    async def test_allowed_call_delegates_to_backend(self) -> None:
        reg, engine = await _setup(ALLOW_ALL)
        backend = _FakeLLMGatewayBackend()
        model_provider = GovernedModelProvider(engine, reg)
        gateway = GatewayModelProvider(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        response = await gateway.chat([{"role": "user", "content": "hi"}], model="claude-sonnet")

        assert response == {"content": "hello", "tokens_out": 5}
        assert backend.calls == [([{"role": "user", "content": "hi"}], "claude-sonnet")]

    async def test_denied_call_never_reaches_backend(self) -> None:
        reg, engine = await _setup(DENY_NO_GRANT_LLM)
        backend = _FakeLLMGatewayBackend()
        model_provider = GovernedModelProvider(engine, reg)
        gateway = GatewayModelProvider(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="No matching grant"):
            await gateway.chat([{"role": "user", "content": "hi"}], model="untrusted-model")

        assert backend.calls == []

    async def test_post_check_deny_raises(self) -> None:
        reg, engine = await _setup(
            ALLOW_ALL,
            PolicyRule(
                name="block-large-response",
                stage=EvaluationStage.POST_LLM,
                expression="result.tokens_out > 1000",
                decision=PolicyDecision.DENY,
                reason="Response too large",
                priority=90,
            ),
        )
        backend = _FakeLLMGatewayBackend(response={"content": "x" * 5000, "tokens_out": 5000})
        model_provider = GovernedModelProvider(engine, reg)
        gateway = GatewayModelProvider(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="too large"):
            await gateway.chat([{"role": "user", "content": "hi"}], model="claude-sonnet")
        # The real backend WAS called -- post-execution validation inspects
        # the real output, it doesn't skip calling the backend.
        assert len(backend.calls) == 1

    async def test_list_models_has_no_pre_llm_check(self) -> None:
        """Discovery, not invocation -- no grant needed to list models."""
        reg, engine = await _setup(DENY_NO_GRANT_LLM)
        backend = _FakeLLMGatewayBackend()
        model_provider = GovernedModelProvider(engine, reg)
        gateway = GatewayModelProvider(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        models = await gateway.list_models()

        assert models == [{"id": "claude-sonnet"}, {"id": "gpt-4"}]

    async def test_health_proxies_backend(self) -> None:
        reg, engine = await _setup()
        backend = _FakeLLMGatewayBackend()
        model_provider = GovernedModelProvider(engine, reg)
        gateway = GatewayModelProvider(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        assert await gateway.health() is True


class TestGatewayToolProvider:
    async def test_list_tools_has_no_pre_tool_check(self) -> None:
        """Discovery, not invocation -- no grant needed to list tools."""
        reg, engine = await _setup(DENY_NO_GRANT_TOOL)
        backend = _FakeToolsGatewayBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        tools = await gateway.list_tools()

        assert tools == [{"name": "database"}, {"name": "web_search"}]

    async def test_call_tool_allowed_delegates_to_backend(self) -> None:
        reg, engine = await _setup(DENY_NO_GRANT_TOOL, ALLOW_ALL)
        backend = _FakeToolsGatewayBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        result = await gateway.call_tool("web_search", {"query": "hello"})

        assert result == {"output": "ok"}
        assert backend.tool_calls == [("web_search", {"query": "hello"})]

    async def test_call_tool_denied_never_reaches_backend(self) -> None:
        reg, engine = await _setup(DENY_NO_GRANT_TOOL)
        backend = _FakeToolsGatewayBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="No matching grant"):
            await gateway.call_tool("database", {"query": "drop everything"})

        assert backend.tool_calls == []

    async def test_delegate_to_agent_allowed_uses_agent_grant_namespace(self) -> None:
        """A real, dedicated test that the agent:<name> resource is checked
        against agent:-namespaced grants, not tool:-namespaced ones --
        proving mcp-gateway.md decision 1's separate grant namespace is
        actually enforced, not just documented."""
        reg, engine = await _setup(DENY_NO_GRANT_TOOL, ALLOW_ALL)
        backend = _FakeToolsGatewayBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        result = await gateway.delegate_to_agent("specialist_researcher", {"task": "research X"})

        assert result == {"output": "ok"}
        assert backend.delegate_calls == [("specialist_researcher", {"task": "research X"})]

    async def test_delegate_to_agent_denied_never_reaches_backend(self) -> None:
        """A tool: grant does NOT implicitly grant an agent: delegation --
        the two namespaces are genuinely separate, not aliases."""
        reg, engine = await _setup(DENY_NO_GRANT_TOOL)
        backend = _FakeToolsGatewayBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="No matching grant"):
            await gateway.delegate_to_agent("unauthorized_agent", {"task": "do something"})

        assert backend.delegate_calls == []

    async def test_call_tool_post_check_deny_raises(self) -> None:
        reg, engine = await _setup(
            DENY_NO_GRANT_TOOL,
            ALLOW_ALL,
            PolicyRule(
                name="block-error-results",
                stage=EvaluationStage.POST_TOOL,
                expression='"error" in result',
                decision=PolicyDecision.DENY,
                reason="Tool returned an error",
                priority=90,
            ),
        )
        backend = _FakeToolsGatewayBackend(result={"error": "boom"})
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="returned an error"):
            await gateway.call_tool("web_search", {"query": "hello"})
        assert len(backend.tool_calls) == 1

    async def test_delegate_to_agent_post_check_deny_raises(self) -> None:
        """Real proof post_check_resource() (not post_check()'s own internal
        tool: prefixing) is what's actually evaluating the agent: resource --
        a policy keyed on a bare "error" in result must still fire."""
        reg, engine = await _setup(
            DENY_NO_GRANT_TOOL,
            ALLOW_ALL,
            PolicyRule(
                name="block-error-results",
                stage=EvaluationStage.POST_TOOL,
                expression='"error" in result',
                decision=PolicyDecision.DENY,
                reason="Delegation returned an error",
                priority=90,
            ),
        )
        backend = _FakeToolsGatewayBackend(result={"error": "boom"})
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="Delegation returned an error"):
            await gateway.delegate_to_agent("specialist_researcher", {"task": "research X"})
        assert len(backend.delegate_calls) == 1

    async def test_health_proxies_backend(self) -> None:
        reg, engine = await _setup()
        backend = _FakeToolsGatewayBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        gateway = GatewayToolProvider(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        assert await gateway.health() is True
