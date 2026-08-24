"""Real end-to-end test: AgentGatewayClient.list_tools()/call_tool() against
an actual running MCP server (fixtures/echo_mcp_server.py, a real
mcp.server.lowlevel.Server + Server.streamable_http_app() + real uvicorn) --
not mocked.

Honest scope note: this connects AgentGatewayClient directly to a real MCP
server, not to a real AgentGateway binary (agentgateway.dev's own Rust
proxy) sitting in front of one. The real, deployed shape is
AgentGatewayClient -> AgentGateway -> upstream MCP server -- this test
proves the client speaks real, correct MCP JSON-RPC over Streamable HTTP
(the actual protocol AgentGateway's own MCP endpoint speaks, confirmed
directly in docs/design/agentgateway-vendor-research-2026-08.md), not that
a real AgentGateway process is exercised. A real AgentGateway binary is a
genuine, separate, higher-effort addition (a real Rust binary + real config
file), named here as a real follow-up, not silently skipped.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator

import pytest

from presidium_contrib.agentgateway.client import AgentGatewayClient, AgentGatewayToolError

_HOST = "127.0.0.1"
_PORT = 8941
_MCP_URL = f"http://{_HOST}:{_PORT}/mcp"


async def _wait_for_port_open(host: str, port: int, timeout_seconds: float = 5.0) -> None:
    """Real readiness poll -- matches test_presidium_server_real_gateway.py's
    own established pattern exactly, not a fixed sleep."""
    async with asyncio.timeout(timeout_seconds):
        while True:
            try:
                _, writer = await asyncio.open_connection(host, port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.02)


@pytest.fixture
async def _running_mcp_server() -> AsyncGenerator[None]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.integration.fixtures.echo_mcp_server",
        str(_PORT),
        cwd=str(__file__.rsplit("/tests/", 1)[0]),
    )
    try:
        await _wait_for_port_open(_HOST, _PORT)
        yield
    finally:
        process.terminate()
        await process.wait()


class TestAgentGatewayClientMcpRealServer:
    async def test_list_tools_returns_real_tools(self, _running_mcp_server: None) -> None:
        client = AgentGatewayClient(mcp_url=_MCP_URL)

        tools = await client.list_tools()

        names = {t["name"] for t in tools}
        assert names == {"add", "always_fails"}
        add_tool = next(t for t in tools if t["name"] == "add")
        assert add_tool["input_schema"]["required"] == ["a", "b"]

    async def test_call_tool_returns_real_result(self, _running_mcp_server: None) -> None:
        client = AgentGatewayClient(mcp_url=_MCP_URL)

        result = await client.call_tool("add", {"a": 4, "b": 5})

        assert result == {"content": "9"}

    async def test_call_tool_raises_on_is_error(self, _running_mcp_server: None) -> None:
        client = AgentGatewayClient(mcp_url=_MCP_URL)

        with pytest.raises(AgentGatewayToolError) as exc_info:
            await client.call_tool("always_fails", {})

        assert exc_info.value.tool_name == "always_fails"

    async def test_mcp_url_defaults_to_base_url_slash_mcp(self) -> None:
        client = AgentGatewayClient("http://example.com:9000")
        assert client._mcp_url == "http://example.com:9000/mcp"  # noqa: SLF001
