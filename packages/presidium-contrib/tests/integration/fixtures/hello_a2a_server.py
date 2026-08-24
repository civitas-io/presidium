"""A real, minimal A2A server -- used by test_agentgateway_a2a_real_server.py to prove
AgentGatewayClient.delegate_to_agent() against an actual running A2A agent, not a mock.

Directly mirrors the real, official a2a-samples Hello World reference agent
(a2aproject/a2a-samples, samples/python/agents/helloworld/{agent_executor,__main__}.py) --
same AgentExecutor shape, same Starlette + real routes + real uvicorn construction, same
create-a-real-Task-then-complete-it behavior (confirmed directly against that source before
writing this, per a2a-delegation-vendor-research-2026-08.md finding 2 -- this is exactly why
the real client-side test needs to handle the completed-Task response shape, not just a bare
Message reply). Reused pattern, not reinvented -- same "mirror the real reference" precedent
this repo already used for echo_mcp_server.py's own docstring.

Honest scope note (same as echo_mcp_server.py's own): this stands in for what a real
AgentGateway A2A route would proxy to. No real AgentGateway binary runs in this test --
AgentGatewayClient connects directly to this fixture's base URL, the same honest-scope
disclaimer test_agentgateway_mcp_real_server.py already states for the MCP side.
"""

from __future__ import annotations

import sys

import uvicorn
from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState
from starlette.applications import Starlette


class HelloWorldAgentExecutor(AgentExecutor):
    """Real Task lifecycle -- WORKING -> artifact with the actual text result -> COMPLETED.
    Verbatim logic from the real a2a-samples reference agent (Apache 2.0), not simplified --
    the whole point of this fixture is proving delegate_to_agent() against the actual shape a
    real A2A agent produces, including the completed-Task response path.
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        task_updater = TaskUpdater(
            event_queue=event_queue, task_id=task.id, context_id=task.context_id
        )
        await task_updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Processing request..."),
        )

        query = get_message_text(context.message)
        if query == "please fail":
            # Real, deliberate failure path -- lets the real client-side test exercise
            # AgentGatewayDelegationError's TaskState check against an actual FAILED task,
            # not a fabricated/mocked one.
            await task_updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message("Failed as requested"),
            )
            return

        result = (
            f"Hello, World! I have received your request ({query})"
            if query
            else "No text input is provided!"
        )

        await task_updater.add_artifact(parts=[new_text_part(text=result, media_type="text/plain")])

        await task_updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Request is completed!"),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancel is not supported.")


def build_app(host: str, port: int) -> Starlette:
    url = f"http://{host}:{port}"
    skill = AgentSkill(
        id="echo_bot",
        name="Echo Bot",
        description="Acknowledges a request and echoes it back in a Hello World message.",
        input_modes=["text/plain"],
        output_modes=["text/plain"],
        tags=["a2a", "echo-example"],
        examples=["hi"],
    )
    agent_card = AgentCard(
        name="Hello World Agent",
        description="Just a hello world agent -- real A2A test fixture",
        version="0.0.1",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0")
        ],
        skills=[skill],
    )
    request_handler = DefaultRequestHandler(
        agent_executor=HelloWorldAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    routes = []
    routes.extend(create_agent_card_routes(agent_card))
    routes.extend(create_jsonrpc_routes(request_handler, "/"))
    return Starlette(routes=routes)


async def serve(host: str, port: int) -> None:
    config = uvicorn.Config(build_app(host, port), host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import anyio

    _host = "127.0.0.1"
    _port = int(sys.argv[1]) if len(sys.argv) > 1 else 8942
    anyio.run(serve, _host, _port)
