"""Registry CRUD over HTTP -- the first of the three surfaces
docs/design/presidium-server.md's own "Deferred: the fuller REST surface" section named as real,
designed intents (registry CRUD, approval request/list/decide, credential resolution) but did
not build in M7's first cut.

One real GenServer per real HTTP route -- NOT the `payload["__op__"]` multi-op-per-agent pattern
that same deferred section originally sketched. That pattern was tried and rejected for
check_grant/health during the ORIGINAL M7 implementation (see gateway_agent.py's own module
docstring for the full story: `payload_extra` is never populated for ordinary, user-declared
routes, confirmed directly against `civitas.gateway.router.RouteTable.from_config()`) -- this
module follows the corrected, verified pattern from the start instead of re-discovering the same
lesson twice.

Every reply is a real HTTP 200 with a JSON-level `"status"` field describing the outcome
(`"registered"`, `"found"`, `"not_found"`, `"deregistered"`, `"error"`), never a non-200 status
and never a raised exception -- a deliberate, documented DIFFERENCE from typical REST status-code
conventions, chosen for two real reasons: (1) it generalizes this milestone's own NFR-1
("fail-closed across the network boundary" -- originally scoped to check_grant, but the same
"never blow up on bad/malicious input" reasoning applies here too) to every registry operation,
not just check_grant; (2) it's the only mechanism this transport actually supports today for an
ordinary `mode: "call"` route -- civitas.gateway.asgi.py's own `__status__` override exists only
for `raw_response=True` routes (built for non-JSON content like Prometheus text exposition), not
general JSON-with-custom-status replies. Using that mechanism here for the first time, for a
JSON body, would be a real, novel usage nothing in this codebase has exercised before; matching
check_grant's own already-tested, working convention instead is the more conservative choice.

**Real, load-bearing constraint, found the hard way and confirmed against the source, not
assumed**: `civitas.gateway.dispatch.py`'s own `_call()` classifies ANY reply payload containing
a top-level `"error"` key as `DispatchStatus.AGENT_ERROR`, which the ASGI layer then maps to a
real HTTP 400 -- regardless of whether anything actually raised. A reply meant to carry a
genuine 200 with an error DESCRIPTION must never use the key name `"error"` at the top level.
`PresidiumGatewayAgent` (gateway_agent.py) already avoided this by using `"reason"` throughout
its own error-shaped replies -- this module follows the exact same convention, not a new one,
and every reply below uses `"reason"`, never `"error"`, for exactly this reason.

Deliberately its own, separate, opt-in GatewayConfig (`build_registry_gateway_config()`), not
merged into `build_check_grant_gateway_config()`'s routes automatically -- registry CRUD is a
materially higher-privilege surface (list every agent, deregister any agent) than "may I invoke
this one action," and this milestone's own FR-4.2 precedent (smallest attack surface by default)
argues for making an operator opt in to exposing it explicitly, on the same or a different
HTTPGateway instance, rather than bundling it in unconditionally.

**Real, honest scope note**: fine-grained authorization over WHO may call these registry
endpoints (beyond the same flat mTLS client-cert-DN allowlist check_grant already has) is a real,
separate, not-yet-built concern -- this module does not invent a permissions model the rest of
this codebase doesn't have yet.
"""

from __future__ import annotations

from typing import Any

from civitas.gateway import GatewayConfig
from civitas.genserver import GenServer

from presidium.errors import AgentNotFoundError
from presidium.registry._base import AgentRegistry
from presidium_contrib.server.serialization import (
    RegistrationRequestError,
    agent_record_from_register_request,
    agent_record_to_dict,
)

DEFAULT_REGISTER_AGENT_NAME = "presidium.registry.register"
DEFAULT_LIST_AGENT_NAME = "presidium.registry.list"
DEFAULT_GET_AGENT_NAME = "presidium.registry.get"
DEFAULT_DEREGISTER_AGENT_NAME = "presidium.registry.deregister"


class RegisterAgentGatewayAgent(GenServer):
    """Exposes AgentRegistry.register() over HTTP -- POST /v1/agents.

    Upsert semantics, matching AgentRegistry.register()'s own real, existing behavior exactly
    (registering an already-known name silently replaces it) -- this HTTP layer does not invent
    a duplicate-detection/409-Conflict concept the underlying registry doesn't actually have.
    """

    def __init__(
        self, name: str = DEFAULT_REGISTER_AGENT_NAME, *, registry: AgentRegistry, **kwargs: Any
    ) -> None:
        super().__init__(name, **kwargs)
        self._agent_registry = registry

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        try:
            record = agent_record_from_register_request(payload)
        except RegistrationRequestError as exc:
            return {"status": "error", "reason": str(exc)}

        registered = await self._agent_registry.register(record)
        return {"status": "registered", "agent": agent_record_to_dict(registered)}


class ListAgentsGatewayAgent(GenServer):
    """Exposes AgentRegistry.list_agents() over HTTP -- GET /v1/agents.

    Real, honest scope note: civitas.gateway's own dispatch does not forward the HTTP request's
    query string into a `mode: "call"` route's payload (confirmed directly -- only the parsed
    JSON body and path params are merged; query_params exists on GatewayRequest for middleware,
    but never reaches handle_call() without a dedicated injection mechanism, which doesn't exist
    here). This endpoint therefore always returns the full, unfiltered list -- status/trust_tier/
    owner filtering (which list_agents() itself already supports, in-process) is a real, named,
    not-yet-built follow-up, not silently missing.
    """

    def __init__(
        self, name: str = DEFAULT_LIST_AGENT_NAME, *, registry: AgentRegistry, **kwargs: Any
    ) -> None:
        super().__init__(name, **kwargs)
        self._agent_registry = registry

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        agents = await self._agent_registry.list_agents()
        return {"status": "ok", "agents": [agent_record_to_dict(a) for a in agents]}


class GetAgentGatewayAgent(GenServer):
    """Exposes AgentRegistry.lookup() over HTTP -- GET /v1/agents/{name}.

    `name` arrives via the route's own {name} path segment, merged into the payload by
    civitas.gateway's dispatch (confirmed directly against civitas/gateway/asgi.py: `payload =
    {**body, **path_params, **entry.payload_extra}`).
    """

    def __init__(
        self, name: str = DEFAULT_GET_AGENT_NAME, *, registry: AgentRegistry, **kwargs: Any
    ) -> None:
        super().__init__(name, **kwargs)
        self._agent_registry = registry

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        agent_name = payload.get("name")
        if not agent_name:
            return {"status": "error", "reason": "Missing path parameter: name"}

        record = await self._agent_registry.lookup(agent_name)
        if record is None:
            return {"status": "not_found", "reason": "Agent not found"}
        return {"status": "found", "agent": agent_record_to_dict(record)}


class DeregisterAgentGatewayAgent(GenServer):
    """Exposes AgentRegistry.deregister() over HTTP -- DELETE /v1/agents/{name}."""

    def __init__(
        self, name: str = DEFAULT_DEREGISTER_AGENT_NAME, *, registry: AgentRegistry, **kwargs: Any
    ) -> None:
        super().__init__(name, **kwargs)
        self._agent_registry = registry

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        agent_name = payload.get("name")
        if not agent_name:
            return {"status": "error", "reason": "Missing path parameter: name"}

        try:
            await self._agent_registry.deregister(agent_name)
        except AgentNotFoundError:
            return {"status": "not_found", "reason": "Agent not found"}
        return {"status": "deregistered"}


def build_registry_gateway_config(
    *,
    host: str = "0.0.0.0",
    port: int = 8444,
    tls_cert: str | None = None,
    tls_key: str | None = None,
    tls_ca_cert: str | None = None,
    require_mtls: bool = True,
    register_agent_name: str = DEFAULT_REGISTER_AGENT_NAME,
    list_agent_name: str = DEFAULT_LIST_AGENT_NAME,
    get_agent_name: str = DEFAULT_GET_AGENT_NAME,
    deregister_agent_name: str = DEFAULT_DEREGISTER_AGENT_NAME,
) -> GatewayConfig:
    """Build the real GatewayConfig for registry CRUD -- POST/GET/DELETE /v1/agents(/{name}).

    Deliberately separate from build_check_grant_gateway_config() -- see this module's own
    docstring for why (a materially higher-privilege surface, opt-in on its own, not bundled).
    Defaults to a different port (8444 vs. check_grant's 8443) so both can run as separate
    HTTPGateway instances in the same Supervisor without a collision if an operator DOES choose
    to run both.

    `register_agent_name`/`list_agent_name`/`get_agent_name`/`deregister_agent_name` MUST match
    the `name=` a real RegisterAgentGatewayAgent/ListAgentsGatewayAgent/GetAgentGatewayAgent/
    DeregisterAgentGatewayAgent instance is constructed with and registered under the same
    Supervisor as the returned HTTPGateway -- this function only builds the routing config, it
    does not construct or register the agents themselves (matching
    build_check_grant_gateway_config()'s own established convention exactly).
    """
    middleware = ["civitas.gateway.mtls.require_client_cert"] if require_mtls else []
    return GatewayConfig(
        host=host,
        port=port,
        tls_cert=tls_cert,
        tls_key=tls_key,
        tls_ca_cert=tls_ca_cert,
        client_cert_mode="required" if require_mtls else "none",
        middleware=middleware,
        routes=[
            {
                "method": "POST",
                "path": "/v1/agents",
                "agent": register_agent_name,
                "mode": "call",
            },
            {
                "method": "GET",
                "path": "/v1/agents",
                "agent": list_agent_name,
                "mode": "call",
            },
            {
                "method": "GET",
                "path": "/v1/agents/{name}",
                "agent": get_agent_name,
                "mode": "call",
            },
            {
                "method": "DELETE",
                "path": "/v1/agents/{name}",
                "agent": deregister_agent_name,
                "mode": "call",
            },
        ],
        docs_enabled=False,
    )
