"""AgentGateway adapter — routes LLM + MCP tool + A2A agent calls through an
AgentGateway instance.

See docs/design/agentgateway-vendor-research-2026-08.md (presidium) for the
real, dated research behind list_tools()/call_tool()'s design; see
docs/design/mcp-gateway.md's "Design decisions, 2026-08-24" for the
resource-naming/method-split decisions this implements exactly.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from a2a.client import create_client
from a2a.client.client import ClientConfig
from a2a.helpers import get_stream_response_text, new_data_message, new_text_message
from a2a.types import Role, SendMessageRequest, StreamResponse, TaskState
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from presidium.errors import PresidiumError

_FAILED_TASK_STATES = frozenset(
    {TaskState.TASK_STATE_FAILED, TaskState.TASK_STATE_REJECTED, TaskState.TASK_STATE_CANCELED}
)

logger = logging.getLogger(__name__)


class AgentGatewayToolError(PresidiumError):
    """Raised when an AgentGateway-proxied MCP tool call reports is_error=True.

    Mirrors civitas-io/fabrica's own MCPToolError shape -- co-located with
    usage here rather than in a shared errors module, matching that same
    project's precedent for a single-adapter-specific error type.
    """

    def __init__(self, tool_name: str, detail: str) -> None:
        self.tool_name = tool_name
        self.detail = detail
        super().__init__(f"AgentGateway tool {tool_name!r} failed: {detail}")


class AgentGatewayDelegationError(PresidiumError):
    """Raised when an A2A delegation cannot be completed.

    Two real, distinct causes, both surfaced through this one error type
    (mirroring AgentGatewayToolError's precedent of one error type per
    adapter operation, not per cause): the target agent name has no
    configured AgentGateway route (a configuration problem, caught before
    any network call), or the target agent itself reported a terminal
    non-success TaskState (FAILED/REJECTED/CANCELED) for the delegated
    request.
    """

    def __init__(self, agent_name_target: str, detail: str) -> None:
        self.agent_name_target = agent_name_target
        self.detail = detail
        super().__init__(f"AgentGateway A2A delegation to {agent_name_target!r} failed: {detail}")


class AgentGatewayClient:
    """HTTP client for AgentGateway's OpenAI-compatible API, plus its MCP
    tool + A2A agent-delegation routing.

    AgentGateway (Linux Foundation) provides unified LLM + MCP + A2A
    routing with native CEL policies and OpenTelemetry. ``chat()``/
    ``list_models()`` wrap its OpenAI-compatible ``/v1/chat/completions``
    endpoint; ``list_tools()``/``call_tool()`` speak real MCP JSON-RPC over
    Streamable HTTP against its MCP proxy endpoint -- confirmed directly
    (not assumed) against AgentGateway's own current docs that this is
    genuine, spec-compliant Streamable HTTP, the same transport
    ``civitas-io/fabrica``'s ``MCPClient`` already uses (GH #26).

    Presidium handles authorization (grants, trust, approval routing) via
    GovernedToolProvider/GovernedModelProvider (through GatewayToolProvider/
    GatewayModelProvider, see presidium/providers/gateway.py) BEFORE calling
    this client. AgentGateway handles operations (routing, rate limiting,
    cost, MCP tool federation, A2A delegation) -- this class never makes an
    authorization decision itself.

    Each MCP call opens a fresh, short-lived session rather than holding a
    persistent connection -- a deliberate simplicity choice, consistent
    with chat()/list_models()/health()'s own existing per-call
    httpx.AsyncClient() pattern, not a performance optimization. Real,
    measured overhead for this (per fabrica's own SPIKE-mcp-transport-
    benchmark.md): ~2ms mean per connection over Streamable HTTP --
    negligible next to any real gateway/tool round trip.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        *,
        api_key: str | None = None,
        default_model: str = "default",
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        mcp_url: str | None = None,
        a2a_routes: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout = timeout
        self._headers: dict[str, str] = headers or {}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._headers.setdefault("Content-Type", "application/json")
        # AgentGateway commonly serves MCP traffic on a separate port/path
        # from LLM traffic (its own "gateways" config can unify them, but
        # doesn't have to) -- mcp_url is a real, independent override, not
        # derived from base_url by default assumption. /mcp matches the
        # path used throughout AgentGateway's own real docs/examples.
        self._mcp_url = mcp_url.rstrip("/") if mcp_url else f"{self._base_url}/mcp"
        # A2A routing is per-upstream-agent, not federated behind one shared endpoint the way
        # MCP tools are -- confirmed directly against AgentGateway's own docs
        # (a2a-delegation-vendor-research-2026-08.md finding 3). There is no "ask the gateway
        # for whichever backend is named X" mechanism, so the caller must supply this mapping
        # explicitly. An empty/omitted map is valid -- it just means no delegation targets are
        # configured yet, matching this class's existing "fail loud on real gaps" discipline
        # rather than guessing a URL shape.
        self._a2a_routes: dict[str, str] = a2a_routes or {}

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat completion request to AgentGateway.

        Returns the full OpenAI-compatible response dict.
        """
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            **kwargs,
        }
        if agent_name:
            body.setdefault("metadata", {})["presidium_agent"] = agent_name

        url = f"{self._base_url}/v1/chat/completions"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json=body,
                headers=self._headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from AgentGateway."""
        url = f"{self._base_url}/v1/models"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=self._headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            raw = data.get("data", [])
            result: list[dict[str, Any]] = list(raw) if isinstance(raw, list) else []
            return result

    async def health(self) -> bool:
        """Check if AgentGateway is reachable."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base_url}/health",
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def list_tools(self, *, agent_name: str | None = None) -> list[dict[str, Any]]:
        """List tools federated behind AgentGateway's MCP endpoint.

        Real MCP ``tools/list`` over Streamable HTTP -- ``agent_name`` is
        accepted for ``ToolsGatewayBackend`` Protocol conformance but not
        currently sent to AgentGateway itself (it has no per-agent tool
        visibility concept as of the version researched, v1.4.1 -- see
        agentgateway-vendor-research-2026-08.md).
        """
        async with (
            streamable_http_client(self._mcp_url) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": dict(tool.input_schema) if tool.input_schema else {},
            }
            for tool in result.tools
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        """Call a tool federated behind AgentGateway's MCP endpoint.

        Real MCP ``tools/call`` over Streamable HTTP. Raises
        ``AgentGatewayToolError`` if the server reports ``is_error=True`` --
        this class never raises a bare, unannotated exception on a tool-
        level failure, matching ``GatewayToolProvider``'s own expectation
        that it can call ``post_check()`` with a real result either way.
        """
        async with (
            streamable_http_client(self._mcp_url) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, arguments)

        texts = [item.text for item in result.content if hasattr(item, "text")]
        if result.is_error:
            detail = " ".join(texts) if texts else str(result.content)
            raise AgentGatewayToolError(name, detail)

        if texts and len(texts) == len(result.content):
            return {"content": "\n".join(texts)}
        return {"content": [str(item) for item in result.content]}

    async def delegate_to_agent(
        self,
        agent_name_target: str,
        arguments: dict[str, Any],
        *,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        """A2A agent delegation over AgentGateway's A2A reverse-proxy routing.

        Real, implemented per a2a-delegation-vendor-research-2026-08.md. Two things that
        finding forced, both different from call_tool()'s MCP shape:

        1. AgentGateway routes A2A per upstream agent (one route per agent server), not
           federated behind one shared endpoint the way MCP tools are -- ``agent_name_target``
           is resolved through ``self._a2a_routes`` (supplied at construction), not derived from
           ``self._base_url``. Raises AgentGatewayDelegationError immediately, before any network
           call, if the target isn't configured -- never guesses a URL shape.
        2. ``arguments`` maps onto A2A's message model, not MCP's flat kwargs: an ``arguments["
           text"]`` key sends a real text message (the common, conversational-delegation case --
           and the only shape a text-only agent like the real a2a-samples Hello World reference
           agent can respond to meaningfully); otherwise the whole dict is sent as a structured
           data message, using A2A's own first-class support for that.

        Extracts the final result via ``get_stream_response_text()`` (handles the completed-Task
        shape the real reference agent actually produces, not just a bare Message reply) and
        raises AgentGatewayDelegationError on a terminal FAILED/REJECTED/CANCELED TaskState,
        rather than returning a successful-looking empty result.
        """
        route = self._a2a_routes.get(agent_name_target)
        if route is None:
            raise AgentGatewayDelegationError(
                agent_name_target,
                "No AgentGateway A2A route configured for this target agent -- pass it in "
                "AgentGatewayClient(a2a_routes={...}) at construction time.",
            )

        text = arguments.get("text")
        message = (
            new_text_message(str(text), role=Role.ROLE_USER)
            if text is not None
            else new_data_message(arguments, role=Role.ROLE_USER)
        )
        if agent_name:
            message.metadata.update({"presidium_agent": agent_name})

        client = await create_client(agent=route, client_config=ClientConfig(streaming=False))
        try:
            request = SendMessageRequest(message=message)
            final: StreamResponse | None = None
            async for chunk in client.send_message(request):
                final = chunk
        finally:
            await client.close()

        if final is None:
            raise AgentGatewayDelegationError(agent_name_target, "No response received")

        if final.HasField("task") and final.task.status.state in _FAILED_TASK_STATES:
            raise AgentGatewayDelegationError(
                agent_name_target,
                f"Task ended in state {TaskState.Name(final.task.status.state)}",
            )

        return {"content": get_stream_response_text(final)}
