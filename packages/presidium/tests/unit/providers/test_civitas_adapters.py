"""Real tests for GovernedModelProviderAdapter/GovernedToolAdapter.

Uses minimal, real (not mocked) fake backends that structurally satisfy
civitas's own ModelProvider/ToolProvider Protocols -- these adapters exist
specifically to BE a civitas.plugins.model.ModelProvider /
civitas.plugins.tools.ToolProvider, so the tests exercise them exactly the
way a real AgentProcess.self.llm/self.tools entry would be used.
"""

from __future__ import annotations

from typing import Any

import pytest
from civitas.plugins.model import ModelResponse

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
from presidium.providers.civitas_adapters import GovernedModelProviderAdapter, GovernedToolAdapter
from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider
from presidium.registry.memory import InMemoryRegistry
from tests.policy_fixtures import ALLOW_ALL


class _FakeModelBackend:
    """A real, minimal civitas.plugins.model.ModelProvider -- structurally,
    not via inheritance (civitas's own ModelProvider is a bare Protocol)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def chat(
        self, model: str, messages: list[dict[str, Any]], tools: list[Any] | None = None
    ) -> ModelResponse:
        self.calls.append((model, messages))
        return ModelResponse(
            content="hello", model=model, tokens_in=10, tokens_out=5, cost_usd=0.01
        )


class _FakeToolBackend:
    """A real, minimal civitas.plugins.tools.ToolProvider."""

    def __init__(self, name: str = "web_search", result: Any = None) -> None:
        self._name = name
        self._result = result if result is not None else {"results": ["a", "b"]}
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"query": {"type": "string"}}}

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._result


async def _setup(*rules: PolicyRule) -> tuple[InMemoryRegistry, CelPolicyEngine]:
    reg = InMemoryRegistry()
    await reg.register(
        AgentRecord(
            agent_id="presidium://local/researcher",
            name="researcher",
            public_key="",
            trust_value=0.5,
            trust_tier=TrustTier.STANDARD,
            grants=[Grant(resources=["tool:web_search"], actions=["invoke"], id="g1")],
        )
    )
    engine = CelPolicyEngine()
    if rules:
        engine.load_policies(list(rules))
    return reg, engine


DENY_LLM = PolicyRule(
    name="deny-llm",
    stage=EvaluationStage.PRE_LLM,
    expression='request.resource == "llm:untrusted-model"',
    decision=PolicyDecision.DENY,
    reason="Untrusted model",
    priority=100,
)

DENY_TOOL = PolicyRule(
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

BLOCK_LARGE_RESPONSE = PolicyRule(
    name="block-large-response",
    stage=EvaluationStage.POST_LLM,
    expression="result.tokens_out > 1000",
    decision=PolicyDecision.DENY,
    reason="Response too large",
    priority=90,
)


class TestGovernedModelProviderAdapter:
    async def test_allowed_call_delegates_to_backend(self) -> None:
        reg, engine = await _setup(ALLOW_ALL)
        backend = _FakeModelBackend()
        model_provider = GovernedModelProvider(engine, reg)
        adapter = GovernedModelProviderAdapter(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        response = await adapter.chat("claude-sonnet", [{"role": "user", "content": "hi"}])

        assert response.content == "hello"
        assert backend.calls == [("claude-sonnet", [{"role": "user", "content": "hi"}])]

    async def test_denied_call_never_reaches_backend(self) -> None:
        reg, engine = await _setup(DENY_LLM)
        backend = _FakeModelBackend()
        model_provider = GovernedModelProvider(engine, reg)
        adapter = GovernedModelProviderAdapter(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="Untrusted model"):
            await adapter.chat("untrusted-model", [{"role": "user", "content": "hi"}])

        assert backend.calls == []

    async def test_post_check_allows_small_output(self) -> None:
        """Confirms POST_LLM policies don't false-positive on the normal case
        (_FakeModelBackend's default tokens_out=5, well under any real
        limit) before the dedicated deny test below."""
        reg, engine = await _setup(BLOCK_LARGE_RESPONSE, ALLOW_ALL)
        backend = _FakeModelBackend()
        model_provider = GovernedModelProvider(engine, reg)
        adapter = GovernedModelProviderAdapter(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        result = await adapter.chat("claude-sonnet", [])
        assert result.content == "hello"

    async def test_post_check_deny_with_large_output(self) -> None:
        reg, engine = await _setup(BLOCK_LARGE_RESPONSE, ALLOW_ALL)

        class _LargeOutputBackend(_FakeModelBackend):
            async def chat(
                self, model: str, messages: list[dict[str, Any]], tools: list[Any] | None = None
            ) -> ModelResponse:
                await super().chat(model, messages, tools)
                return ModelResponse(content="x" * 5000, model=model, tokens_in=10, tokens_out=5000)

        backend = _LargeOutputBackend()
        model_provider = GovernedModelProvider(engine, reg)
        adapter = GovernedModelProviderAdapter(
            backend=backend, model_provider=model_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="too large"):
            await adapter.chat("claude-sonnet", [])
        # The real backend WAS called (post-execution validation, not pre) --
        # confirming this isn't accidentally skipping the real call.
        assert len(backend.calls) == 1


class TestGovernedToolAdapter:
    async def test_name_and_schema_proxy_the_real_backend(self) -> None:
        reg, engine = await _setup()
        backend = _FakeToolBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        adapter = GovernedToolAdapter(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        assert adapter.name == "web_search"
        assert adapter.schema == backend.schema

    async def test_allowed_call_delegates_to_backend(self) -> None:
        reg, engine = await _setup(DENY_TOOL, ALLOW_ALL)
        backend = _FakeToolBackend()
        tool_provider = GovernedToolProvider(engine, reg)
        adapter = GovernedToolAdapter(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        result = await adapter.execute(query="hello")

        assert result == {"results": ["a", "b"]}
        assert backend.calls == [{"query": "hello"}]

    async def test_denied_call_never_reaches_backend(self) -> None:
        reg, engine = await _setup(DENY_TOOL)
        backend = _FakeToolBackend(name="database")  # no grant for "database"
        tool_provider = GovernedToolProvider(engine, reg)
        adapter = GovernedToolAdapter(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="No matching grant"):
            await adapter.execute(query="drop everything")

        assert backend.calls == []

    async def test_non_dict_result_wrapped_for_post_check(self) -> None:
        """Real tool outputs aren't always dicts -- a bare string/list/number
        result must not crash post_check(), which expects dict[str, Any]."""
        reg, engine = await _setup(DENY_TOOL, ALLOW_ALL)
        backend = _FakeToolBackend(result="a bare string result")
        tool_provider = GovernedToolProvider(engine, reg)
        adapter = GovernedToolAdapter(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        result = await adapter.execute(query="hello")

        assert result == "a bare string result"

    async def test_post_check_deny_raises(self) -> None:
        reg, engine = await _setup(
            DENY_TOOL,
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
        backend = _FakeToolBackend(result={"error": "boom"})
        tool_provider = GovernedToolProvider(engine, reg)
        adapter = GovernedToolAdapter(
            backend=backend, tool_provider=tool_provider, agent_name="researcher"
        )

        with pytest.raises(PolicyDeniedError, match="returned an error"):
            await adapter.execute(query="hello")
        # The real backend WAS called -- post-execution validation inspects
        # the real output, it doesn't skip calling the tool.
        assert len(backend.calls) == 1
