"""A real, minimal MCP server exposed over Streamable HTTP -- used by
test_agentgateway_mcp_real_server.py to prove AgentGatewayClient's real
list_tools()/call_tool() against an actual running MCP server, not a mock.

Directly mirrors civitas-io/fabrica's own
tests/mcp/fixtures/echo_http_server.py (same tool shape, same
mcp.server.lowlevel.Server + Server.streamable_http_app() + uvicorn
construction) -- reused pattern, not reinvented, since this is standing in
for what a real AgentGateway instance would proxy to in the real deployment
shape (AgentGateway -> real upstream MCP server), even though this test
connects AgentGatewayClient directly to this fixture (no real AgentGateway
binary in CI) -- see the test module's own docstring for the honest scope
note this implies.
"""

from __future__ import annotations

import sys

import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server

_ADD_SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
    "required": ["a", "b"],
}
_FAIL_SCHEMA = {"type": "object", "properties": {}}


async def _on_list_tools(ctx: object, params: object) -> types.ListToolsResult:
    return types.ListToolsResult(
        tools=[
            types.Tool(name="add", description="Add two numbers", input_schema=_ADD_SCHEMA),
            types.Tool(
                name="always_fails",
                description="Always returns is_error=True",
                input_schema=_FAIL_SCHEMA,
            ),
        ]
    )


async def _on_call_tool(ctx: object, params: types.CallToolRequestParams) -> types.CallToolResult:
    if params.name == "add":
        args = params.arguments or {}
        total = args["a"] + args["b"]
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(total))])
    if params.name == "always_fails":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="simulated failure")],
            is_error=True,
        )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=f"unknown tool: {params.name}")],
        is_error=True,
    )


def build_app(host: str) -> object:
    server: Server[None] = Server(
        "echo-agentgateway-test-server", on_list_tools=_on_list_tools, on_call_tool=_on_call_tool
    )
    return server.streamable_http_app(host=host)


async def serve(host: str, port: int) -> None:
    config = uvicorn.Config(build_app(host), host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import anyio

    _host = "127.0.0.1"
    _port = int(sys.argv[1]) if len(sys.argv) > 1 else 8940
    anyio.run(serve, _host, _port)
