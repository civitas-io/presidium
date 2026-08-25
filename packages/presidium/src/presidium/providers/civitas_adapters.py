"""Real civitas.plugins.{model,tools} Protocol implementations.

Civitas is generic — it has no concept of governance. Presidium is the
opinionated layer that wraps a real backend (a real `ModelProvider`/
`ToolProvider`) with policy enforcement, producing something that still
*is* a real Civitas `ModelProvider`/`ToolProvider` — a drop-in replacement
for `self.llm`/an entry in `self.tools`, not a separate, parallel API.

**Real, load-bearing design constraint, not invented**: neither
`civitas.plugins.model.ModelProvider.chat()` nor
`civitas.plugins.tools.ToolProvider.execute()` carries agent identity in its
own call signature — `self.llm`/`self.tools` are typically shared across a
whole Supervisor tree (`agent.llm = self.llm` on spawn, per
`civitas/supervisor.py`). These adapters are therefore constructed **per
agent**, with `agent_name` bound at construction time — the exact,
already-established pattern `civitas.process.AgentProcess.connect_mcp()`
already uses for `civitas-io/fabrica`'s own `MCPTool`
(`MCPTool(client, schema, ..., agent_name=self.name)`), not a new one
invented here.

DENY (and a denied REQUIRE_APPROVAL) **raise** `PolicyDeniedError` — reusing
`GovernedModelProvider.check()`/`GovernedToolProvider.check()`'s existing,
unmodified behavior exactly. This is a real, deliberate difference from
`presidium_contrib.server`'s `check_grant()` path: an in-process Python
exception through the calling agent's own error boundary/supervision is the
correct, idiomatic Civitas convention here — there is no HTTP boundary to
keep from raising across.
"""

from __future__ import annotations

import logging
from typing import Any

from civitas.plugins.model import ModelProvider, ModelResponse
from civitas.plugins.tools import ToolProvider
from civitas.supervisor import DynamicSupervisor

from presidium.model import EnforcementMode, PolicyDecision
from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider

logger = logging.getLogger(__name__)


class GovernedModelProviderAdapter:
    """A real `civitas.plugins.model.ModelProvider` — checks, then delegates.

    Assign to a governed agent's own `self.llm` (or return from a
    `model_for`-style method) to make every `self.llm.chat(...)` call go
    through Presidium's policy engine first, transparently.
    """

    def __init__(
        self,
        *,
        backend: ModelProvider,
        model_provider: GovernedModelProvider,
        agent_name: str,
    ) -> None:
        self._backend = backend
        self._model_provider = model_provider
        self._agent_name = agent_name

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Check PRE_LLM policy, delegate to the real backend, check POST_LLM.

        Raises `PolicyDeniedError` on a PRE_LLM or POST_LLM deny — the real
        backend is never called at all on a PRE_LLM deny, and a POST_LLM
        deny propagates even though the real response was already obtained
        (post-execution validation exists precisely to catch and block bad
        output after seeing it).
        """
        await self._model_provider.check(self._agent_name, model)

        response = await self._backend.chat(model, messages, tools)

        result_data: dict[str, Any] = {
            "content": response.content,
            "model": response.model,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost_usd": response.cost_usd,
        }
        await self._model_provider.post_check(self._agent_name, model, result_data)

        return response


class GovernedToolAdapter:
    """A real `civitas.plugins.tools.ToolProvider` — checks, then delegates.

    Wraps exactly one real underlying tool (`ToolProvider` represents a
    single named tool, unlike `GovernedToolProvider`'s own multi-tool
    check()/check_grant() interface) — register the returned adapter into a
    governed agent's own `self.tools` in place of the real tool directly.
    """

    def __init__(
        self,
        *,
        backend: ToolProvider,
        tool_provider: GovernedToolProvider,
        agent_name: str,
    ) -> None:
        self._backend = backend
        self._tool_provider = tool_provider
        self._agent_name = agent_name

    @property
    def name(self) -> str:
        return self._backend.name

    @property
    def schema(self) -> dict[str, Any]:
        return self._backend.schema

    async def execute(self, **kwargs: Any) -> Any:
        """Check PRE_TOOL policy, delegate to the real backend, check POST_TOOL.

        Raises `PolicyDeniedError` on a PRE_TOOL or POST_TOOL deny — the
        real tool is never invoked at all on a PRE_TOOL deny.
        """
        await self._tool_provider.check(self._agent_name, self.name)

        result = await self._backend.execute(**kwargs)

        # Real tool outputs are commonly already dict-shaped (JSON-like APIs);
        # a non-dict result (a string, a number, a list) is wrapped under a
        # single "value" key so post_check() always has a dict to evaluate,
        # matching EvaluationContext.result's own dict[str, Any] contract.
        result_data: dict[str, Any] = result if isinstance(result, dict) else {"value": result}
        await self._tool_provider.post_check(self._agent_name, self.name, "invoke", result_data)

        return result


async def governed_spawn_check(
    *,
    tool_provider: GovernedToolProvider,
    spawner: str,
    agent_class: type,
    name: str,
    config: dict[str, Any],
) -> bool:
    """Real, reusable ``on_spawn_requested()`` logic (`civitas.supervisor.
    DynamicSupervisor`'s own governance veto hook) -- closes a real, external gap:
    the hook exists and works, but nothing wired it to Presidium's policy engine.

    Call this directly from a custom ``DynamicSupervisor`` subclass's own
    ``on_spawn_requested`` override (for a caller who already has other
    overrides to combine with); use :class:`GovernedDynamicSupervisor` below
    instead for the common case of "just gate every spawn through Presidium."

    ``resource`` is ``f"agent:{agent_class.__name__}"`` -- authorizing by the
    KIND of agent being spawned, matching the existing ``agent:<name>`` grant
    namespace (``GatewayToolProvider.delegate_to_agent()``,
    ``check_resource()``'s own docstring) -- not the caller-chosen, unpredictable
    runtime ``name``, which is instead passed through as ``parameters["name"]``
    alongside the rest of ``config`` for a CEL policy to inspect if it wants
    finer-grained control (e.g. deny a specific dangerous config flag).

    ``spawner`` is ``DynamicSupervisor.current_spawner`` -- read it INSIDE your
    ``on_spawn_requested`` override, where the property is valid, and pass it
    here (this function does not have access to the supervisor instance
    itself). An empty string (`DynamicSupervisor`'s own default for an
    unattributed/administrative spawn request -- see
    ``civitas/supervisor.py``'s ``_handle_spawn``) needs no special-casing
    here: ``check_grant()``'s own existing "agent not found in registry"
    path already fails closed for an empty/unrecognized name, for free.

    Uses ``check_grant()``, not ``check()``/``check_resource()`` -- deliberately:
    ``on_spawn_requested``'s own contract is bool-returning, not exception-based,
    the same reasoning ``civitas-io/fabrica``'s own ``execute_in_sandbox`` already
    follows for exactly this kind of value-based caller. REQUIRE_APPROVAL is
    treated as a deny under HARD enforcement -- there is no suspend/resume
    mechanism available at this call site to block a spawn pending approval
    (`on_spawn_requested` must resolve synchronously to a bool); ADVISORY/SOFT
    enforcement never blocks the spawn, only logs, matching
    ``check_resource()``'s own established enforcement-mode semantics.
    """
    result = await tool_provider.check_grant(
        spawner,
        resource=f"agent:{agent_class.__name__}",
        action="spawn",
        parameters={"name": name, **config},
    )

    if result.enforcement in (EnforcementMode.ADVISORY, EnforcementMode.SOFT):
        if result.decision != PolicyDecision.ALLOW:
            logger.info(
                "spawn.%s spawner=%s agent_class=%s name=%s policy=%s "
                "(enforcement=%s, not blocking)",
                result.decision.value,
                spawner,
                agent_class.__name__,
                name,
                result.policy_name,
                result.enforcement.value,
            )
        return True

    if result.decision != PolicyDecision.ALLOW:
        logger.warning(
            "spawn.%s spawner=%s agent_class=%s name=%s policy=%s reason=%s",
            result.decision.value,
            spawner,
            agent_class.__name__,
            name,
            result.policy_name,
            result.reason,
        )

    return result.decision == PolicyDecision.ALLOW


class GovernedDynamicSupervisor(DynamicSupervisor):
    """Ready-to-use ``DynamicSupervisor`` for the common case: gate every
    dynamic spawn through Presidium with no custom subclass of your own.

    ``spawner_allowlist``/``max_children``/etc. (any other real
    ``DynamicSupervisor`` constructor argument) still work unchanged --
    forwarded via ``**kwargs``, evaluated BEFORE this class's own
    ``on_spawn_requested`` override runs (`civitas/supervisor.py`'s own
    ``_handle_spawn`` checks those first).
    """

    def __init__(self, name: str, *, tool_provider: GovernedToolProvider, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._presidium_tool_provider = tool_provider

    async def on_spawn_requested(
        self, agent_class: type, name: str, config: dict[str, Any]
    ) -> bool:
        return await governed_spawn_check(
            tool_provider=self._presidium_tool_provider,
            spawner=self.current_spawner or "",
            agent_class=agent_class,
            name=name,
            config=config,
        )
