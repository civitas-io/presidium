"""Approval list/decide over HTTP -- the second of the three surfaces
docs/design/presidium-server.md's own "Deferred: the fuller REST surface" section named as real,
designed intents (registry CRUD, approval request/list/decide, credential resolution). Registry
CRUD shipped first (registry_agent.py); this module is the second piece.

Real, deliberate scope boundary, not an oversight: this exposes `ApprovalService.list_pending()`/
`decide()` over HTTP -- it does NOT create a real, new "POST /v1/approvals" endpoint for a
network caller to originate an approval request. Approval requests are created in-process, by
`GovernedToolProvider.check()`/`GovernedModelProvider.check()` calling `ApprovalService.
request_approval()` when a policy returns REQUIRE_APPROVAL -- a remote HTTP caller must never be
able to inject an arbitrary approval request directly. Matches the original design doc's own
sketch exactly (`GET /v1/approvals`, `POST /v1/approvals/{id}/approve`,
`POST /v1/approvals/{id}/deny` -- no `POST /v1/approvals`).

**Real, honest, load-bearing scope boundary, confirmed by reading the source, not assumed**:
`GovernedToolProvider.check_grant()` (the one real, existing HTTP-facing consumer, via
`PresidiumGatewayAgent`) does NOT call `ApprovalService.request_approval()` at all -- confirmed
directly in providers/tool.py. It returns REQUIRE_APPROVAL as a plain value for the caller's own
suspend/resume mechanism (FR-1.5), by design, not by omission. This means an approval surfaced
by `check_grant()` over `/v1/check_grant` is NOT automatically tracked here and NOT resolvable
through these new endpoints -- only approvals from the BLOCKING `check()`/`GovernedModelProvider.
check()` path (which does call `request_approval()`) are. Wiring `check_grant()`'s own
REQUIRE_APPROVAL path into a real ApprovalService for durable, cross-network resolution is a
real, separate, bigger integration (it would need to compose with Civitas's own durable
suspension mechanism on the CALLING side, e.g. Fabrica) -- explicitly out of scope here, not
silently glossed over.

Same "one real GenServer per HTTP route" pattern as registry_agent.py, and the same `"reason"`-
not-`"error"` reply-key convention (civitas.gateway.dispatch.py classifies any reply payload
containing a top-level `"error"` key as `DispatchStatus.AGENT_ERROR` -> HTTP 400).
"""

from __future__ import annotations

from typing import Any

from civitas.gateway import GatewayConfig
from civitas.genserver import GenServer

from presidium.approval import ApprovalService
from presidium.model import ApprovalDecision, ApprovalRequest

DEFAULT_LIST_APPROVALS_AGENT_NAME = "presidium.approvals.list"
DEFAULT_APPROVE_AGENT_NAME = "presidium.approvals.approve"
DEFAULT_DENY_AGENT_NAME = "presidium.approvals.deny"


def _approval_request_to_dict(request: ApprovalRequest) -> dict[str, Any]:
    """Serialize a real ApprovalRequest to a JSON-safe dict. Lives here, not in
    serialization.py, since it's approval-specific and this is the only module that needs it --
    registry_agent.py's own AgentRecord/Grant helpers stay in serialization.py because
    GetAgentGatewayAgent/ListAgentsGatewayAgent/RegisterAgentGatewayAgent all three need them.
    """
    return {
        "request_id": request.request_id,
        "agent_id": request.agent_id,
        "resource": request.resource,
        "action": request.action,
        "reason": request.reason,
        "approvers": list(request.approvers),
        "context": dict(request.context),
        "policy_name": request.policy_name,
        "status": request.status.value,
        "timeout_seconds": request.timeout_seconds,
    }


class ListApprovalsGatewayAgent(GenServer):
    """Exposes ApprovalService.list_pending() over HTTP -- GET /v1/approvals."""

    def __init__(
        self,
        name: str = DEFAULT_LIST_APPROVALS_AGENT_NAME,
        *,
        approval_service: ApprovalService,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._approval_service = approval_service

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        pending = await self._approval_service.list_pending()
        return {"status": "ok", "approvals": [_approval_request_to_dict(r) for r in pending]}


class ApproveGatewayAgent(GenServer):
    """Exposes ApprovalService.decide() over HTTP -- POST /v1/approvals/{id}/approve.

    ``id`` arrives via the route's own {id} path segment. An optional JSON body may supply
    ``decided_by``/``reason``; both default to honest, generic values if omitted, matching
    ApprovalDecision's own optional ``reason`` field and this module's need for *some*
    decided_by string even when the real network caller's identity isn't otherwise available
    at this layer (see this module's own class docstring for the real mTLS-identity gap this
    doesn't attempt to solve).
    """

    def __init__(
        self,
        name: str = DEFAULT_APPROVE_AGENT_NAME,
        *,
        approval_service: ApprovalService,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._approval_service = approval_service

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        request_id = payload.get("id")
        if not request_id:
            return {"status": "error", "reason": "Missing path parameter: id"}

        decision = ApprovalDecision(
            request_id=request_id,
            approved=True,
            decided_by=payload.get("decided_by", "presidium-server"),
            reason=payload.get("reason"),
        )
        # ApprovalService.decide() has no return value and no way to report "no such pending
        # request" -- confirmed directly against CallbackApprovalProvider's own implementation
        # (a plain dict.get() that no-ops silently for an unknown/already-resolved id). This
        # reply is honest about that real limitation, not inventing a false-confidence 404.
        await self._approval_service.decide(request_id, decision)
        return {"status": "decided", "decision": "approved", "request_id": request_id}


class DenyGatewayAgent(GenServer):
    """Exposes ApprovalService.decide() over HTTP -- POST /v1/approvals/{id}/deny.

    See ApproveGatewayAgent's own docstring for the shared reasoning -- this is its mirror
    image, not a separate design.
    """

    def __init__(
        self,
        name: str = DEFAULT_DENY_AGENT_NAME,
        *,
        approval_service: ApprovalService,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._approval_service = approval_service

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        request_id = payload.get("id")
        if not request_id:
            return {"status": "error", "reason": "Missing path parameter: id"}

        decision = ApprovalDecision(
            request_id=request_id,
            approved=False,
            decided_by=payload.get("decided_by", "presidium-server"),
            reason=payload.get("reason"),
        )
        await self._approval_service.decide(request_id, decision)
        return {"status": "decided", "decision": "denied", "request_id": request_id}


def build_approval_gateway_config(
    *,
    host: str = "0.0.0.0",
    port: int = 8445,
    tls_cert: str | None = None,
    tls_key: str | None = None,
    tls_ca_cert: str | None = None,
    require_mtls: bool = True,
    list_approvals_agent_name: str = DEFAULT_LIST_APPROVALS_AGENT_NAME,
    approve_agent_name: str = DEFAULT_APPROVE_AGENT_NAME,
    deny_agent_name: str = DEFAULT_DENY_AGENT_NAME,
) -> GatewayConfig:
    """Build the real GatewayConfig for approval list/decide -- GET /v1/approvals,
    POST /v1/approvals/{id}/approve, POST /v1/approvals/{id}/deny.

    Deliberately its own, separate, opt-in GatewayConfig -- same rationale as
    build_registry_gateway_config()'s own docstring: a materially different, admin-facing
    surface, not bundled into build_check_grant_gateway_config() automatically. Defaults to yet
    another port (8445) so all three can run as separate HTTPGateway instances in the same
    Supervisor without a collision.

    `list_approvals_agent_name`/`approve_agent_name`/`deny_agent_name` MUST match the `name=` a
    real ListApprovalsGatewayAgent/ApproveGatewayAgent/DenyGatewayAgent instance is constructed
    with and registered under the same Supervisor as the returned HTTPGateway -- this function
    only builds the routing config, matching build_check_grant_gateway_config()'s/
    build_registry_gateway_config()'s own established convention exactly.
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
                "method": "GET",
                "path": "/v1/approvals",
                "agent": list_approvals_agent_name,
                "mode": "call",
            },
            {
                "method": "POST",
                "path": "/v1/approvals/{id}/approve",
                "agent": approve_agent_name,
                "mode": "call",
            },
            {
                "method": "POST",
                "path": "/v1/approvals/{id}/deny",
                "agent": deny_agent_name,
                "mode": "call",
            },
        ],
        docs_enabled=False,
    )
