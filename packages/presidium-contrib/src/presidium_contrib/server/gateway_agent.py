"""PresidiumGatewayAgent — thin HTTP-to-GovernedRuntime translation layer.

No governance logic of its own. Every real decision (agent lookup, policy
evaluation, audit emission) is GovernedRuntime's — see docs/design/
presidium-server.md for the full design and the "why not the separately-
deployed PolicyEvaluatorServer/RegistryServer GenServers" rationale.

Built on ``civitas.genserver.GenServer`` (not a plain ``AgentProcess``,
which would need ``self.reply()`` called from inside a live dispatch
context) — the same base class ``PolicyEvaluatorServer``/``RegistryServer``
already use, for the same reason: a synchronous request/reply agent that
returns plain dicts is easy to unit-test directly (``handle_call(payload,
"sender")``) without needing a running Runtime/Supervisor.

**Real, corrected design note (found during implementation, not assumed):**
An earlier draft of this module dispatched on a single agent via a
``payload["__op__"]`` marker, injected through each route's
``payload_extra`` — modeled on Civitas's own auto-registered topology
routes, which do exactly this. Verified directly against
``civitas.gateway.router.RouteTable.from_config()`` (the real parser for
user-declared ``routes:`` config) that **``payload_extra`` is never
populated for ordinary, user-declared routes** — it is exclusively set by
Civitas's own internal ``_build_topology_routes()`` construction, not a
general-purpose mechanism exposed through ``GatewayConfig.routes``'s public,
list-of-dicts shape. Confirmed with a real, running gateway before writing
this note (an actual `GET /health` returned `400 {"error": "Unknown
operation: None"}` — the marker never arrived). Fixed by using one real
agent per route instead — genuinely simpler, and correctly matches the real,
verified API surface.
"""

from __future__ import annotations

from typing import Any

from civitas.gateway import GatewayConfig
from civitas.gateway.ratelimit import RateLimiter
from civitas.genserver import GenServer

from presidium.model import PolicyDecision
from presidium.runtime import GovernedRuntime

#: The names PresidiumGatewayAgent/HealthCheckAgent register under by
#: default, and the "agent" values build_check_grant_gateway_config()
#: points its two routes at.
DEFAULT_AGENT_NAME = "presidium.gateway"
DEFAULT_HEALTH_AGENT_NAME = "presidium.gateway.health"

#: civitas.gateway.ratelimit.rate_limit's own middleware function has this
#: name HARDCODED as a private module constant -- confirmed by reading its
#: source directly, not assumed. A RateLimiter GenServer wired alongside
#: PresidiumGatewayAgent/HealthCheckAgent in the same Supervisor MUST be
#: registered under exactly this name -- confirmed directly against
#: civitas.bus.MessageBus.request(): an unregistered recipient raises
#: MessageRoutingError immediately (no silent fail-open, no 30s hang
#: waiting on a timeout). Kept here, not re-derived at every call site,
#: since civitas's own constant is
#: private (`_RATE_LIMITER_NAME`) and not meant to be imported across
#: package boundaries.
RATE_LIMITER_AGENT_NAME = "rate_limiter"


class PresidiumGatewayAgent(GenServer):
    """Exposes GovernedRuntime.tool_provider.check_grant() over HTTP.

    Call protocol:

        {"agent_id": "...", "action": "...", "scope": {...}}
        → {"decision": "allow"|"deny"|"require_approval", "reason": ..., "approval_context": ...}
    """

    def __init__(
        self, name: str = DEFAULT_AGENT_NAME, *, runtime: GovernedRuntime, **kwargs: Any
    ) -> None:
        super().__init__(name, **kwargs)
        self._runtime = runtime

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        """Implements FR-1 (presidium-server-requirements.md) exactly:
        fail-closed on a missing/unresolvable agent_id, never raises.
        """
        agent_id = payload.get("agent_id")
        action = payload.get("action")
        # FR-1.4: `scope` (Fabrica's own cross-surface Scope type) is opaque to Presidium --
        # deserialized straight through into ActionRequest.parameters so a CEL policy MAY
        # reference it (e.g. `request.parameters.tenant_id`); never interpreted here. A real,
        # previously-unfixed gap: this field used to be silently discarded -- FR-1.1's own
        # documented request body has always included it, but nothing downstream ever read it.
        scope = payload.get("scope")

        if not agent_id or not action:
            return {
                "decision": "deny",
                "reason": "Missing required field: 'agent_id' and 'action' are both required",
                "approval_context": None,
            }

        if scope is not None and not isinstance(scope, dict):
            return {
                "decision": "deny",
                "reason": "Invalid field: 'scope' must be an object if present",
                "approval_context": None,
            }

        record = await self._runtime.registry.lookup_by_id(agent_id)
        if record is None:
            return {
                "decision": "deny",
                "reason": "Agent not found in registry",
                "approval_context": None,
            }

        # FR-1.3 ("Option 2, refined"): resource = action verbatim,
        # Presidium's own `action` field is the fixed, generic verb "invoke".
        result = await self._runtime.tool_provider.check_grant(
            record.name, resource=action, action="invoke", parameters=scope
        )

        approval_context: dict[str, Any] | None = None
        if result.decision == PolicyDecision.REQUIRE_APPROVAL:
            approval_context = {
                "policy_name": result.policy_name,
                "reason": result.reason,
                "approvers": result.approvers,
            }

        return {
            "decision": result.decision.value,
            "reason": result.reason,
            "approval_context": approval_context,
        }


class HealthCheckAgent(GenServer):
    """A real, minimal, always-`{"status": "ok"}` GenServer for `/health`.

    Deliberately its own tiny agent rather than a second responsibility on
    PresidiumGatewayAgent — see this module's own docstring for why a single
    dispatch-by-payload-marker agent doesn't work with Civitas's real,
    verified route API, and single-responsibility is a genuine improvement
    on top of just working around that, not merely a workaround.
    """

    def __init__(self, name: str = DEFAULT_HEALTH_AGENT_NAME, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        return {"status": "ok"}


def build_check_grant_gateway_config(
    *,
    host: str = "0.0.0.0",
    port: int = 8443,
    tls_cert: str | None = None,
    tls_key: str | None = None,
    tls_ca_cert: str | None = None,
    require_mtls: bool = True,
    agent_name: str = DEFAULT_AGENT_NAME,
    health_agent_name: str = DEFAULT_HEALTH_AGENT_NAME,
    rate_limit: bool = False,
) -> GatewayConfig:
    """Build the real, minimal GatewayConfig for check_grant() + /health.

    Deliberately does NOT set ``topology_agent`` (FR-4.2) — a security
    product's own network-facing API gets the smallest attack surface
    consistent with its real job, not Civitas's full 11-route topology
    introspection surface by default.

    ``require_mtls=True`` (the default) wires ``civitas.gateway.mtls.
    require_client_cert`` and requires ``tls_cert``/``tls_key``/``tls_ca_cert``
    to be real paths (FR-3.1/FR-3.3) — the operator supplies a dedicated
    private CA, never a public/broad one. Set ``require_mtls=False`` only for
    local development against a plaintext loopback deployment.

    ``agent_name``/``health_agent_name`` MUST match the ``name=`` a real
    ``PresidiumGatewayAgent``/``HealthCheckAgent`` instance is constructed
    with and registered under the same Supervisor as the returned
    ``HTTPGateway`` — this function only builds the routing config, it does
    not construct or register the agents themselves.

    ``rate_limit=False`` by default -- opt-in, not opt-out -- wires Civitas's own first-party
    ``civitas.gateway.ratelimit.rate_limit`` middleware onto ``/v1/check_grant`` specifically,
    NOT ``/health`` -- a liveness probe must never be rejected because real traffic used up the
    budget. Defaults to disabled, unlike ``require_mtls``: rate limiting is an availability/
    operational control with real tuning implications (the wrong ``max_requests`` can reject
    legitimate traffic), not a fail-closed security boundary the way mTLS is -- an opt-in
    default, not an oversight. **This is a pure boolean toggle, not a place to configure
    ``max_requests``/``window_seconds`` -- those live on ``build_rate_limiter()`` instead, so
    there is exactly one place those numbers are ever set, not two.** When enabled, the caller
    MUST also construct and register a real ``civitas.gateway.ratelimit.RateLimiter`` GenServer,
    named exactly ``RATE_LIMITER_AGENT_NAME`` ("rate_limiter"), in the same Supervisor as the
    returned ``HTTPGateway`` -- this function only builds the routing config; see
    ``build_rate_limiter()`` for a real, ready-made constructor with the name already correct.
    """
    # Global (config.middleware) and per-route middleware are CONCATENATED per request, not
    # deduplicated -- confirmed directly against civitas.gateway.asgi.py's own dispatch
    # (`self._middlewares + route_middlewares`). mTLS goes in the global list (applies
    # uniformly, exactly once per request); rate limiting goes ONLY in check_grant's own
    # per-route list -- putting mTLS there too would silently run it twice.
    middleware = ["civitas.gateway.mtls.require_client_cert"] if require_mtls else []
    check_grant_middleware = ["civitas.gateway.ratelimit.rate_limit"] if rate_limit else []
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
                "path": "/v1/check_grant",
                "agent": agent_name,
                "mode": "call",
                "middleware": check_grant_middleware,
            },
            {
                "method": "GET",
                "path": "/health",
                "agent": health_agent_name,
                "mode": "call",
            },
        ],
        docs_enabled=False,
    )


def build_rate_limiter(
    max_requests: int,
    window_seconds: float = 60.0,
    *,
    name: str = RATE_LIMITER_AGENT_NAME,
) -> RateLimiter:
    """Real, ready-made ``civitas.gateway.ratelimit.RateLimiter`` GenServer for
    ``build_check_grant_gateway_config(rate_limit=True)``.

    A thin constructor wrapper, not a new mechanism -- ``RateLimiter`` is Civitas's own
    first-party G4 rate limiter (sliding-window, per-client-IP), re-exposed here purely for
    discoverability: without this, a caller wiring up an M7 server would need to know to reach
    into ``civitas.gateway.ratelimit`` directly AND separately know the exact, hardcoded
    ``"rate_limiter"`` name that middleware's own lookup requires -- both are handled here.

    Construct once and add to the same ``Supervisor`` children list as the ``HTTPGateway``/
    ``PresidiumGatewayAgent``/``HealthCheckAgent`` -- e.g.
    ``Supervisor("root", children=[gateway, gateway_agent, health_agent,
    build_rate_limiter(100, 60.0)])``.
    """
    return RateLimiter(name, max_requests=max_requests, window_seconds=window_seconds)
