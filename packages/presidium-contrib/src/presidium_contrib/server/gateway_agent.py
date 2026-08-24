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
from civitas.genserver import GenServer

from presidium.model import PolicyDecision
from presidium.runtime import GovernedRuntime

#: The names PresidiumGatewayAgent/HealthCheckAgent register under by
#: default, and the "agent" values build_check_grant_gateway_config()
#: points its two routes at.
DEFAULT_AGENT_NAME = "presidium.gateway"
DEFAULT_HEALTH_AGENT_NAME = "presidium.gateway.health"


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
                "path": "/v1/check_grant",
                "agent": agent_name,
                "mode": "call",
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
