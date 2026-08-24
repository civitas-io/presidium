# Vendor research: A2A delegation (`a2a-sdk` + AgentGateway's A2A proxy), 2026-08-24

**Status:** Research complete, feeds directly into `AgentGatewayClient.delegate_to_agent()`'s
implementation. **Why now:** `agentgateway-vendor-research-2026-08.md` (this session, earlier)
named this as a real, explicit follow-up (finding 4: A2A is a genuinely different wire protocol
from MCP) but did not itself research the A2A side — every claim below is sourced directly
against the current `a2a-sdk` PyPI metadata, the real `a2a-python` repository source, the real
`a2a-samples` Hello World reference agent, and AgentGateway's own current A2A docs, not carried
over from the earlier research's assumptions about what A2A "probably" looks like.

---

## 1. The official Python SDK: `a2a-sdk`, currently `1.1.2`

[`a2a-sdk`](https://pypi.org/project/a2a-sdk/) (Google LLC, Apache 2.0, `a2aproject/a2a-python`
on GitHub) implements A2A Protocol Specification `1.0` (with a `0.3` compatibility mode).
`requires-python = ">=3.10"` — compatible with this org's `>=3.12` floor. Core dependencies:
`httpx>=0.28.1`, `pydantic>=2.11.3`, `protobuf`, `json-rpc` — no conflict with anything already
in this org's dependency tree. The core install has **no extras needed for client-side use**
(`fastapi`/`grpc`/`sql*` extras are all server-side or transport-specific; a pure client doesn't
need any of them).

## 2. Real, confirmed client API shape — genuinely different from MCP's `ClientSession`

Confirmed directly against the real `a2a-samples` Hello World reference client
(`samples/python/agents/helloworld/test_client.py`) and the real `a2a-python` source
(`src/a2a/client/client_factory.py`, `src/a2a/helpers/proto_helpers.py`):

- `a2a.client.create_client(agent: str | AgentCard, client_config: ClientConfig | None = None,
  ...) -> Client` — accepts either a plain base URL string (resolves the agent card internally)
  or an already-fetched `AgentCard`. No separate manual `A2ACardResolver` step is required for
  the common case (the Hello World sample's own doc-example uses one explicitly to *show* the
  resolution step, but `create_client` does it internally when given a URL).
- `a2a.client.ClientConfig(streaming: bool = ...)` — streaming vs. non-streaming is a client-side
  choice, not a server capability negotiation the caller has to detect first.
- Message construction goes through helper functions in `a2a.helpers`, not a raw dataclass
  constructor: `new_text_message(text, role=Role.ROLE_USER)` for plain text, **`new_data_message(
  data: Any, role=...)` for arbitrary JSON-serializable structured data** — confirmed directly in
  `proto_helpers.py`. This is the real, load-bearing finding for this integration: A2A has a
  first-class structured-data message type, not just conversational text.
- `client.send_message(SendMessageRequest(message=...))` returns an `AsyncIterator[
  StreamResponse]` — even in non-streaming mode, still an async generator (yields once, in
  practice, for a synchronous exchange). `StreamResponse` is a real protobuf oneof-shaped message
  with `task`/`message`/`status_update`/`artifact_update` fields.
- **`a2a.helpers.get_stream_response_text(response, delimiter="\n") -> str`** uniformly extracts
  the real text content regardless of which of those four fields is populated (message text,
  task artifact text, status-update message text, or artifact-update text) — the correct, single
  extraction point to use rather than branching on the oneof manually.
- `Task.status.state` is a real `TaskState` enum (`TASK_STATE_COMPLETED`/`_FAILED`/`_CANCELED`/
  `_INPUT_REQUIRED`/`_REJECTED`/`_AUTH_REQUIRED`/...) — a completed exchange needs to check this,
  not just assume any non-exception response succeeded.

**Confirmed directly against the real Hello World reference agent's own server-side
`agent_executor.py`**: it creates a real `Task` (not a bare `Message` reply) — `TASK_STATE_WORKING`
→ artifact-with-text-result → `TASK_STATE_COMPLETED`. Any real end-to-end test against this
specific reference agent must handle the `task` branch of `StreamResponse`, not just `message`
— confirmed by reading the actual behavior, not assumed from the protocol spec alone.

## 3. AgentGateway's A2A proxy — confirmed to be exactly what `agentgateway-vendor-research-
   2026-08.md` predicted, with one new, concrete, load-bearing detail

Confirmed directly against AgentGateway's own current docs (`agentgateway.dev/docs/standalone/
latest/agent/a2a/`, the A2A proxy guide): **an A2A backend is a plain HTTP host — AgentGateway
adds an `a2a: {}` policy to a route, which then rewrites the target agent's own agent card
(`/.well-known/agent.json`) so its `url` field points back at the gateway itself**, preventing a
client from bypassing the gateway on follow-up requests. All standard gateway policies (CORS,
auth, authz, rate limiting) apply uniformly to A2A traffic once that policy is set.

**The new, concrete, load-bearing detail this research adds**: AgentGateway's A2A routing is
**one route per upstream A2A agent server**, unlike MCP where AgentGateway federates every
backend tool behind a single unified endpoint addressable by tool name. There is no
"AgentGateway, give me whichever backend is named `<agent_name_target>`" mechanism — a client
must already know which gateway-fronted base URL serves a given target agent. This directly
shapes `AgentGatewayClient.delegate_to_agent()`'s real design: it needs an explicit
`agent_name_target -> gateway route base URL` mapping supplied at construction time, not a single
shared `a2a_url` the way `call_tool()` has a single shared `mcp_url`.

## 4. What this means for the real implementation

- New dependency: `a2a-sdk>=1.1.2` on the `[agentgateway]` extra (client-only usage, no extras of
  `a2a-sdk` itself needed).
- `AgentGatewayClient.__init__` gains `a2a_routes: dict[str, str] | None = None` — an explicit,
  named map from target agent name to the AgentGateway route base URL that fronts it. Fails
  loudly (a new `AgentGatewayDelegationError`, not `NotImplementedError` or a silent no-op) for
  an unconfigured target, matching this class's own existing "never silently guess" discipline.
- `arguments: dict[str, Any]` (the existing `delegate_to_agent()` signature, unchanged, matching
  `call_tool()`'s shape) needs a real mapping onto A2A's message model: if `arguments` contains a
  `"text"` key, send it as `new_text_message(...)` (the common, real, conversational-delegation
  case — and the only shape the Hello World reference agent can meaningfully respond to, since
  its own `get_message_text()`-based query extraction finds nothing in a data-only message);
  otherwise send the whole dict via `new_data_message(arguments)` (the structured-data case for
  agents built to consume it, per A2A's own first-class support for this).
- Response extraction uses `get_stream_response_text()` uniformly (handles the completed-`Task`
  case the real reference agent actually exercises), with an explicit `TaskState` check raising
  `AgentGatewayDelegationError` on `_FAILED`/`_REJECTED`/`_CANCELED` rather than returning a
  successful-looking empty result.
