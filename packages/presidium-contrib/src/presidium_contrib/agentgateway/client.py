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
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from presidium.errors import PresidiumError

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
        """A2A agent delegation -- NOT YET IMPLEMENTED.

        Deliberately deferred, per agentgateway-vendor-research-2026-08.md
        finding 4 and mcp-gateway.md's own "Design decisions, 2026-08-24"
        §3: AgentGateway's A2A support is a genuinely different wire
        protocol (a pure HTTP reverse proxy, agent cards, ``message/
        stream``) from its MCP support, needing a real, new ``a2a-sdk``
        dependency this class does not have yet. Raising explicitly rather
        than silently returning a stub result.
        """
        raise NotImplementedError(
            "AgentGatewayClient.delegate_to_agent() is not implemented yet -- A2A delegation "
            "needs a real a2a-sdk client, a separate, explicit follow-up. See "
            "docs/design/agentgateway-vendor-research-2026-08.md finding 4."
        )
