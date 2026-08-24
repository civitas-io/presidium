"""Real end-to-end test: an actual civitas.gateway.HTTPGateway, an actual
civitas.Runtime/Supervisor, an actual httpx client over real HTTP -- proving approval list/
decide works as a real, deployed HTTP surface. Mirrors test_registry_gateway_real_http.py's own
established pattern exactly, applied to build_approval_gateway_config().
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import httpx
import pytest
from civitas import Runtime, Supervisor
from civitas.gateway import HTTPGateway

from presidium.approval import CallbackApprovalProvider
from presidium.model import ApprovalRequest
from presidium_contrib.server import (
    ApproveGatewayAgent,
    DenyGatewayAgent,
    ListApprovalsGatewayAgent,
    build_approval_gateway_config,
)

_PORT = 19446
_BASE_URL = f"http://127.0.0.1:{_PORT}"


def _make_request(request_id: str) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=request_id,
        agent_id="presidium://acme.com/researcher",
        resource="tool:database",
        action="write",
        reason="Low trust write",
        approvers=["security@acme.com"],
        context={},
        policy_name="trust-gate",
        timeout_seconds=5.0,
    )


async def _wait_for_port_open(host: str, port: int, timeout_seconds: float = 5.0) -> None:
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
async def _running_approval_gateway() -> AsyncGenerator[CallbackApprovalProvider]:
    service = CallbackApprovalProvider()
    gateway_config = build_approval_gateway_config(port=_PORT, require_mtls=False)
    gateway = HTTPGateway("approval-api", config=gateway_config)
    list_agent = ListApprovalsGatewayAgent(approval_service=service)
    approve_agent = ApproveGatewayAgent(approval_service=service)
    deny_agent = DenyGatewayAgent(approval_service=service)

    supervisor = Supervisor("root", children=[gateway, list_agent, approve_agent, deny_agent])
    civitas_runtime = Runtime(supervisor=supervisor)
    await civitas_runtime.start()
    try:
        try:
            await _wait_for_port_open("127.0.0.1", _PORT)
        except (OSError, TimeoutError):
            pass
        await asyncio.sleep(0.05)
        yield service
    finally:
        await civitas_runtime.stop()


class TestApprovalGatewayRealHttp:
    async def test_list_empty_over_real_http(
        self, _running_approval_gateway: CallbackApprovalProvider
    ) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_BASE_URL}/v1/approvals", timeout=5.0)

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "approvals": []}

    async def test_list_returns_a_real_pending_request_over_real_http(
        self, _running_approval_gateway: CallbackApprovalProvider
    ) -> None:
        service = _running_approval_gateway
        task = asyncio.ensure_future(service.request_approval(_make_request("req-1")))
        await asyncio.sleep(0.05)

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_BASE_URL}/v1/approvals", timeout=5.0)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["approvals"]) == 1
        assert body["approvals"][0]["request_id"] == "req-1"
        assert body["approvals"][0]["status"] == "pending"

        async with httpx.AsyncClient() as client:
            await client.post(f"{_BASE_URL}/v1/approvals/req-1/approve", timeout=5.0)
        await task

    async def test_approve_over_real_http_resolves_the_real_pending_request(
        self, _running_approval_gateway: CallbackApprovalProvider
    ) -> None:
        service = _running_approval_gateway
        task = asyncio.ensure_future(service.request_approval(_make_request("req-1")))
        await asyncio.sleep(0.05)

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{_BASE_URL}/v1/approvals/req-1/approve", timeout=5.0)

        assert resp.status_code == 200
        assert resp.json() == {"status": "decided", "decision": "approved", "request_id": "req-1"}

        decision = await task
        assert decision.approved is True

    async def test_deny_over_real_http_resolves_the_real_pending_request(
        self, _running_approval_gateway: CallbackApprovalProvider
    ) -> None:
        service = _running_approval_gateway
        task = asyncio.ensure_future(service.request_approval(_make_request("req-1")))
        await asyncio.sleep(0.05)

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{_BASE_URL}/v1/approvals/req-1/deny", timeout=5.0)

        assert resp.status_code == 200
        assert resp.json() == {"status": "decided", "decision": "denied", "request_id": "req-1"}

        decision = await task
        assert decision.approved is False

    async def test_approve_unknown_request_id_over_real_http_is_a_real_honest_noop(
        self, _running_approval_gateway: CallbackApprovalProvider
    ) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{_BASE_URL}/v1/approvals/ghost/approve", timeout=5.0)

        assert resp.status_code == 200
        assert resp.json() == {"status": "decided", "decision": "approved", "request_id": "ghost"}
