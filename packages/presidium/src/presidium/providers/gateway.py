"""LLMGatewayBackend/ToolsGatewayBackend -- operations delegated to an external
gateway process (AgentGateway today), as opposed to civitas_adapters.py's
direct, in-process Civitas ModelProvider/ToolProvider wrapping.

See docs/design/llm-gateway.md and docs/design/mcp-gateway.md's own
"Design decisions, 2026-08-24" section for the full reasoning -- this file
implements exactly what those sections specify, not more.

Real, load-bearing distinction from civitas_adapters.py's
GovernedModelProviderAdapter/GovernedToolAdapter: those wrap a real,
directly-constructed civitas.plugins.{model,tools} Protocol object (no
external process). GatewayModelProvider/GatewayToolProvider wrap a real,
separate, network-reachable gateway process -- the backend Protocols here
return raw OpenAI-style/MCP-style dicts, not civitas's ModelResponse/
ToolProvider shapes, which is why this needed its own composition classes
rather than reusing civitas_adapters.py's directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider


@runtime_checkable
class LLMGatewayBackend(Protocol):
    """Operations backend for GatewayModelProvider: routing, rate limits, cost tracking.

    Presidium owns authorization (grants, trust, CEL policy) and always runs it BEFORE this is
    called. The backend owns operations -- it never sees a request Presidium already denied.

    AgentGatewayClient's real chat()/list_models()/health() already satisfy this shape exactly,
    structurally, with zero changes needed -- confirmed directly against its current source.
    """

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def list_models(self) -> list[dict[str, Any]]: ...

    async def health(self) -> bool: ...


@runtime_checkable
class ToolsGatewayBackend(Protocol):
    """Operations backend for GatewayToolProvider: MCP tool + A2A agent-delegation routing.

    Presidium owns authorization and always runs it BEFORE call_tool()/delegate_to_agent() is
    called. list_tools() is deliberately NOT authorization-gated -- see mcp-gateway.md's
    "Design decisions, 2026-08-24" §4 (discovery, not invocation).
    """

    async def list_tools(self, *, agent_name: str | None = None) -> list[dict[str, Any]]: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        agent_name: str | None = None,
    ) -> dict[str, Any]: ...

    async def delegate_to_agent(
        self,
        agent_name_target: str,
        arguments: dict[str, Any],
        *,
        agent_name: str | None = None,
    ) -> dict[str, Any]: ...

    async def health(self) -> bool: ...


class GatewayModelProvider:
    """Composes a GovernedModelProvider (authorization) with an LLMGatewayBackend (operations).

    Bound to one agent_name at construction, matching civitas_adapters.py's established
    per-agent-construction precedent.
    """

    def __init__(
        self,
        *,
        backend: LLMGatewayBackend,
        model_provider: GovernedModelProvider,
        agent_name: str,
    ) -> None:
        self._backend = backend
        self._model_provider = model_provider
        self._agent_name = agent_name

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Check PRE_LLM policy, delegate to the real gateway backend, check POST_LLM.

        Raises PolicyDeniedError on a PRE_LLM or POST_LLM deny -- the backend is never called
        at all on a PRE_LLM deny.
        """
        model_name = model or "default"
        await self._model_provider.check(self._agent_name, model_name)

        response = await self._backend.chat(
            messages, model=model, agent_name=self._agent_name, **kwargs
        )

        await self._model_provider.post_check(self._agent_name, model_name, response)
        return response

    async def list_models(self) -> list[dict[str, Any]]:
        """No PRE_LLM check -- discovery, not invocation, matching list_tools()'s own
        exemption for the identical reason."""
        return await self._backend.list_models()

    async def health(self) -> bool:
        return await self._backend.health()


class GatewayToolProvider:
    """Composes a GovernedToolProvider (authorization) with a ToolsGatewayBackend (operations).

    Bound to one agent_name at construction, matching civitas_adapters.py's established
    per-agent-construction precedent. See mcp-gateway.md's "Design decisions, 2026-08-24" for
    the full reasoning behind call_tool()/delegate_to_agent() being two methods, not one.
    """

    def __init__(
        self,
        *,
        backend: ToolsGatewayBackend,
        tool_provider: GovernedToolProvider,
        agent_name: str,
    ) -> None:
        self._backend = backend
        self._tool_provider = tool_provider
        self._agent_name = agent_name

    async def list_tools(self) -> list[dict[str, Any]]:
        """No PRE_TOOL check -- discovery, not invocation. See mcp-gateway.md decision 4."""
        return await self._backend.list_tools(agent_name=self._agent_name)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """resource = f"tool:{name}" -- check, delegate, post_check.

        Raises PolicyDeniedError on a PRE_TOOL or POST_TOOL deny -- the backend is never called
        at all on a PRE_TOOL deny, matching GovernedToolAdapter's existing convention exactly.
        """
        await self._tool_provider.check(self._agent_name, name)

        result = await self._backend.call_tool(name, arguments, agent_name=self._agent_name)

        await self._tool_provider.post_check(self._agent_name, name, "invoke", result)
        return result

    async def delegate_to_agent(
        self, agent_name_target: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """resource = f"agent:{agent_name_target}" -- otherwise identical shape to call_tool().

        A separate grant namespace from tool:<name> (mcp-gateway.md decision 1) -- an agent
        granted tool:database:read is not automatically granted agent:specialist_researcher.
        Uses GovernedToolProvider.check_resource() (a real, added-alongside-this-file method) to
        get check()'s exact raise-on-deny/require-approval/enforcement-mode handling against a
        verbatim, non-tool:-prefixed resource string -- not a private-method reach-in, not a
        duplicated re-implementation.
        """
        resource = f"agent:{agent_name_target}"
        await self._tool_provider.check_resource(self._agent_name, resource, "invoke")

        result = await self._backend.delegate_to_agent(
            agent_name_target, arguments, agent_name=self._agent_name
        )

        await self._tool_provider.post_check_resource(self._agent_name, resource, "invoke", result)
        return result

    async def health(self) -> bool:
        return await self._backend.health()
