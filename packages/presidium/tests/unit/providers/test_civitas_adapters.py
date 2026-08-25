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
    EnforcementMode,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine
from presidium.providers.civitas_adapters import (
    GovernedDynamicSupervisor,
    GovernedModelProviderAdapter,
    GovernedToolAdapter,
    governed_spawn_check,
)
from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider
from presidium.registry.memory import InMemoryRegistry
from tests.policy_fixtures import ALLOW_ALL


class _WorkerAgent:
    """Stands in for a real class dynamically spawned via DynamicSupervisor --
    only its __name__ matters (used to build the "agent:<class name>" resource)."""


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


ALLOW_SPAWN = PolicyRule(
    name="allow-spawn",
    stage=EvaluationStage.PRE_TOOL,
    expression='request.resource == "agent:_WorkerAgent" && request.action == "spawn"',
    decision=PolicyDecision.ALLOW,
    reason="Spawner may spawn workers",
    priority=100,
)

DENY_SPAWN = PolicyRule(
    name="deny-spawn",
    stage=EvaluationStage.PRE_TOOL,
    expression='request.resource == "agent:_WorkerAgent" && request.action == "spawn"',
    decision=PolicyDecision.DENY,
    reason="Not allowed to spawn workers",
    priority=100,
)

ADVISORY_DENY_SPAWN = PolicyRule(
    name="advisory-deny-spawn",
    stage=EvaluationStage.PRE_TOOL,
    expression='request.resource == "agent:_WorkerAgent" && request.action == "spawn"',
    decision=PolicyDecision.DENY,
    reason="Discouraged but not blocked",
    priority=100,
    enforcement=EnforcementMode.ADVISORY,
)


class TestGovernedSpawnCheck:
    """governed_spawn_check() -- closes a real, externally-reported gap:
    DynamicSupervisor.on_spawn_requested had no Presidium reference
    integration at all."""

    async def test_allowed_spawn_returns_true(self) -> None:
        reg, engine = await _setup(ALLOW_SPAWN)
        tool_provider = GovernedToolProvider(engine, reg)

        approved = await governed_spawn_check(
            tool_provider=tool_provider,
            spawner="researcher",
            agent_class=_WorkerAgent,
            name="worker-1",
            config={"task": "scrape"},
        )

        assert approved is True

    async def test_denied_spawn_returns_false(self) -> None:
        reg, engine = await _setup(DENY_SPAWN)
        tool_provider = GovernedToolProvider(engine, reg)

        approved = await governed_spawn_check(
            tool_provider=tool_provider,
            spawner="researcher",
            agent_class=_WorkerAgent,
            name="worker-1",
            config={},
        )

        assert approved is False

    async def test_unattributed_spawner_denied_via_existing_registry_miss(self) -> None:
        """No special-casing needed: an unattributed spawner ("" -- civitas's
        own DynamicSupervisor default for an administrative spawn request)
        naturally fails closed via check_grant()'s existing "agent not found
        in registry" path."""
        reg, engine = await _setup(ALLOW_SPAWN)
        tool_provider = GovernedToolProvider(engine, reg)

        approved = await governed_spawn_check(
            tool_provider=tool_provider,
            spawner="",
            agent_class=_WorkerAgent,
            name="worker-1",
            config={},
        )

        assert approved is False

    async def test_unmatched_request_denies_by_default(self) -> None:
        """No policy at all -> CelPolicyEngine's real, current fail-closed
        default (DENY) -- spawning is not silently approved just because
        nobody wrote a spawn-specific rule."""
        reg, engine = await _setup()
        tool_provider = GovernedToolProvider(engine, reg)

        approved = await governed_spawn_check(
            tool_provider=tool_provider,
            spawner="researcher",
            agent_class=_WorkerAgent,
            name="worker-1",
            config={},
        )

        assert approved is False

    async def test_advisory_deny_never_blocks_the_spawn(self) -> None:
        """ADVISORY/SOFT enforcement never blocks -- matches check_resource()'s
        own established enforcement-mode semantics exactly."""
        reg, engine = await _setup(ADVISORY_DENY_SPAWN)
        tool_provider = GovernedToolProvider(engine, reg)

        approved = await governed_spawn_check(
            tool_provider=tool_provider,
            spawner="researcher",
            agent_class=_WorkerAgent,
            name="worker-1",
            config={},
        )

        assert approved is True

    async def test_config_and_name_are_visible_to_the_policy(self) -> None:
        """The spawned instance's caller-chosen name and config are threaded
        into request.parameters, not just the agent_class resource string --
        lets a policy make finer-grained decisions than "class name alone."""
        reg, engine = await _setup(
            PolicyRule(
                name="deny-dangerous-config",
                stage=EvaluationStage.PRE_TOOL,
                expression='request.resource == "agent:_WorkerAgent" '
                "&& request.parameters.dangerous == true",
                decision=PolicyDecision.DENY,
                reason="Dangerous config flag set",
                priority=100,
            ),
            ALLOW_SPAWN,
        )
        tool_provider = GovernedToolProvider(engine, reg)

        safe = await governed_spawn_check(
            tool_provider=tool_provider,
            spawner="researcher",
            agent_class=_WorkerAgent,
            name="worker-1",
            config={"dangerous": False},
        )
        dangerous = await governed_spawn_check(
            tool_provider=tool_provider,
            spawner="researcher",
            agent_class=_WorkerAgent,
            name="worker-2",
            config={"dangerous": True},
        )

        assert safe is True
        assert dangerous is False


class TestGovernedDynamicSupervisor:
    """The ready-to-use subclass -- delegates to governed_spawn_check() using
    self.current_spawner, exactly the way a hand-written on_spawn_requested
    override would."""

    async def test_delegates_to_governed_spawn_check(self) -> None:
        reg, engine = await _setup(ALLOW_SPAWN)
        tool_provider = GovernedToolProvider(engine, reg)
        supervisor = GovernedDynamicSupervisor("sup", tool_provider=tool_provider)

        # Simulate being inside on_spawn_requested's call window, the same
        # way civitas/supervisor.py's own _handle_spawn does.
        supervisor._current_spawner = "researcher"
        try:
            approved = await supervisor.on_spawn_requested(_WorkerAgent, "worker-1", {})
        finally:
            supervisor._current_spawner = None

        assert approved is True

    async def test_denied_spawn_via_supervisor(self) -> None:
        reg, engine = await _setup(DENY_SPAWN)
        tool_provider = GovernedToolProvider(engine, reg)
        supervisor = GovernedDynamicSupervisor("sup", tool_provider=tool_provider)

        supervisor._current_spawner = "researcher"
        try:
            approved = await supervisor.on_spawn_requested(_WorkerAgent, "worker-1", {})
        finally:
            supervisor._current_spawner = None

        assert approved is False

    async def test_other_dynamicsupervisor_kwargs_still_work(self) -> None:
        """Real DynamicSupervisor constructor args (max_children, etc.) pass
        through **kwargs unaffected -- this subclass doesn't shadow them."""
        reg, engine = await _setup(ALLOW_SPAWN)
        tool_provider = GovernedToolProvider(engine, reg)
        supervisor = GovernedDynamicSupervisor("sup", tool_provider=tool_provider, max_children=5)

        assert supervisor.max_children == 5
