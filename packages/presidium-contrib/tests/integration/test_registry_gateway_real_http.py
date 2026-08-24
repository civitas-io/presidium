"""Real end-to-end test: an actual civitas.gateway.HTTPGateway, an actual
civitas.Runtime/Supervisor, an actual httpx client over real HTTP -- proving registry CRUD
works as a real, deployed HTTP surface, not just its GenServers in isolation. Mirrors
test_presidium_server_real_gateway.py's own established pattern exactly, applied to
build_registry_gateway_config() instead of build_check_grant_gateway_config().

Uses require_mtls=False (a real, supported, documented local-development mode) -- a full
private-CA + client-cert handshake test already exists for check_grant
(test_presidium_server_mtls.py); config-level mTLS wiring is identical here (same
civitas.gateway.mtls.require_client_cert middleware), not re-tested per endpoint.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import httpx
import pytest
from civitas import Runtime, Supervisor
from civitas.gateway import HTTPGateway

from presidium.registry.memory import InMemoryRegistry
from presidium_contrib.server import (
    DeregisterAgentGatewayAgent,
    GetAgentGatewayAgent,
    ListAgentsGatewayAgent,
    RegisterAgentGatewayAgent,
    build_registry_gateway_config,
)

_PORT = 19445
_BASE_URL = f"http://127.0.0.1:{_PORT}"


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
async def _running_registry_gateway() -> AsyncGenerator[InMemoryRegistry]:
    registry = InMemoryRegistry()
    gateway_config = build_registry_gateway_config(port=_PORT, require_mtls=False)
    gateway = HTTPGateway("registry-api", config=gateway_config)
    register_agent = RegisterAgentGatewayAgent(registry=registry)
    list_agent = ListAgentsGatewayAgent(registry=registry)
    get_agent = GetAgentGatewayAgent(registry=registry)
    deregister_agent = DeregisterAgentGatewayAgent(registry=registry)

    supervisor = Supervisor(
        "root",
        children=[gateway, register_agent, list_agent, get_agent, deregister_agent],
    )
    civitas_runtime = Runtime(supervisor=supervisor)
    await civitas_runtime.start()
    try:
        try:
            await _wait_for_port_open("127.0.0.1", _PORT)
        except (OSError, TimeoutError):
            pass
        await asyncio.sleep(0.05)
        yield registry
    finally:
        await civitas_runtime.stop()


class TestRegistryGatewayRealHttp:
    async def test_register_over_real_http(
        self, _running_registry_gateway: InMemoryRegistry
    ) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE_URL}/v1/agents",
                json={
                    "agent_id": "presidium://acme.com/researcher",
                    "name": "researcher",
                    "public_key": "a2V5",
                    "owner": "alice@acme.com",
                },
                timeout=5.0,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "registered"
        assert body["agent"]["name"] == "researcher"
        assert body["agent"]["owner"] == "alice@acme.com"

    async def test_register_missing_field_over_real_http(
        self, _running_registry_gateway: InMemoryRegistry
    ) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE_URL}/v1/agents", json={"agent_id": "presidium://acme.com/x"}, timeout=5.0
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_list_over_real_http(self, _running_registry_gateway: InMemoryRegistry) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{_BASE_URL}/v1/agents",
                json={
                    "agent_id": "presidium://acme.com/a",
                    "name": "a",
                    "public_key": "a2V5",
                },
                timeout=5.0,
            )
            resp = await client.get(f"{_BASE_URL}/v1/agents", timeout=5.0)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert [a["name"] for a in body["agents"]] == ["a"]

    async def test_get_by_name_over_real_http(
        self, _running_registry_gateway: InMemoryRegistry
    ) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{_BASE_URL}/v1/agents",
                json={
                    "agent_id": "presidium://acme.com/researcher",
                    "name": "researcher",
                    "public_key": "a2V5",
                },
                timeout=5.0,
            )
            resp = await client.get(f"{_BASE_URL}/v1/agents/researcher", timeout=5.0)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "found"
        assert body["agent"]["name"] == "researcher"

    async def test_get_unknown_agent_over_real_http(
        self, _running_registry_gateway: InMemoryRegistry
    ) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_BASE_URL}/v1/agents/ghost", timeout=5.0)

        assert resp.status_code == 200
        assert resp.json() == {"status": "not_found", "reason": "Agent not found"}

    async def test_deregister_over_real_http(
        self, _running_registry_gateway: InMemoryRegistry
    ) -> None:
        registry = _running_registry_gateway
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{_BASE_URL}/v1/agents",
                json={
                    "agent_id": "presidium://acme.com/researcher",
                    "name": "researcher",
                    "public_key": "a2V5",
                },
                timeout=5.0,
            )
            resp = await client.delete(f"{_BASE_URL}/v1/agents/researcher", timeout=5.0)

        assert resp.status_code == 200
        assert resp.json() == {"status": "deregistered"}
        assert await registry.lookup("researcher") is None

    async def test_deregister_unknown_agent_over_real_http(
        self, _running_registry_gateway: InMemoryRegistry
    ) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{_BASE_URL}/v1/agents/ghost", timeout=5.0)

        assert resp.status_code == 200
        assert resp.json() == {"status": "not_found", "reason": "Agent not found"}

    async def test_get_and_post_on_same_path_route_to_different_agents(
        self, _running_registry_gateway: InMemoryRegistry
    ) -> None:
        """Real, explicit proof that /v1/agents (GET) and /v1/agents (POST) -- same path,
        different method -- correctly dispatch to their own separate agents, not a shared one
        confused by method."""
        async with httpx.AsyncClient() as client:
            list_before = await client.get(f"{_BASE_URL}/v1/agents", timeout=5.0)
            await client.post(
                f"{_BASE_URL}/v1/agents",
                json={"agent_id": "presidium://acme.com/a", "name": "a", "public_key": "a2V5"},
                timeout=5.0,
            )
            list_after = await client.get(f"{_BASE_URL}/v1/agents", timeout=5.0)

        assert list_before.json()["agents"] == []
        assert len(list_after.json()["agents"]) == 1
