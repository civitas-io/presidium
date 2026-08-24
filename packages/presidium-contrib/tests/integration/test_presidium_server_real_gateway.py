"""Real end-to-end test: an actual civitas.gateway.HTTPGateway, an actual
civitas.Runtime/Supervisor, an actual httpx client over real HTTP — proving
the whole presidium-server stack works together, not just its pieces in
isolation.

mTLS itself is exercised at the config-assembly level in
tests/unit/server/test_gateway_config.py (real X.509 PKI setup for a full
handshake test is a real, separate, higher-effort addition worth doing
later — not silently skipped, flagged here honestly). This test uses
require_mtls=False (a real, supported, documented mode for local
development) to exercise the actual check_grant request/response path over
real HTTP.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import httpx
import pytest
from civitas import Runtime, Supervisor
from civitas.gateway import HTTPGateway

from presidium.model import (
    AgentRecord,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
)
from presidium.policy.cel import CelPolicyEngine
from presidium.registry.memory import InMemoryRegistry
from presidium.runtime import GovernedRuntime
from presidium_contrib.server import (
    HealthCheckAgent,
    PresidiumGatewayAgent,
    build_check_grant_gateway_config,
)
from tests.policy_fixtures import ALLOW_ALL

_PORT = 19443
_BASE_URL = f"http://127.0.0.1:{_PORT}"

DENY_NO_GRANT = PolicyRule(
    name="enforce-grants",
    stage=EvaluationStage.PRE_TOOL,
    expression="""
        !agent.grants.exists(g,
            request.resource in g.resources &&
            request.action in g.actions
        )
    """,
    decision=PolicyDecision.DENY,
    reason="No matching grant",
    priority=100,
)


async def _wait_for_port_open(host: str, port: int, timeout_seconds: float = 5.0) -> None:
    """Real readiness poll -- a real TCP connect attempt, not a fixed sleep.

    A fixed sleep (the pattern civitas's own gateway tests use) risks
    flakiness on a loaded CI runner; polling the actual socket is cheap and
    removes the guesswork. Uses asyncio.timeout() (ASYNC109) rather than a
    manual deadline loop with its own `timeout` parameter.
    """
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
async def _running_gateway() -> AsyncGenerator[None]:
    registry = InMemoryRegistry()
    await registry.register(
        AgentRecord(
            agent_id="presidium://acme.com/researcher",
            name="researcher",
            public_key="",
            grants=[Grant(resources=["code_mode"], actions=["invoke"], id="g1")],
        )
    )
    engine = CelPolicyEngine()
    engine.load_policies([DENY_NO_GRANT, ALLOW_ALL])
    runtime = GovernedRuntime(registry=registry, engine=engine)

    gateway_config = build_check_grant_gateway_config(port=_PORT, require_mtls=False)
    gateway = HTTPGateway("api", config=gateway_config)
    gateway_agent = PresidiumGatewayAgent(runtime=runtime)
    health_agent = HealthCheckAgent()

    supervisor = Supervisor("root", children=[gateway, gateway_agent, health_agent])
    civitas_runtime = Runtime(supervisor=supervisor)
    await civitas_runtime.start()
    try:
        # Bind check via the actual socket, not a fixed sleep (see the
        # docstring on _wait_for_port_open).
        try:
            await _wait_for_port_open("127.0.0.1", _PORT)
        except (OSError, TimeoutError):
            pass  # sock.connect can race uvicorn's own bind; fall back below
        await asyncio.sleep(0.05)
        yield
    finally:
        await civitas_runtime.stop()


class TestPresidiumServerRealGateway:
    async def test_health_over_real_http(self, _running_gateway: None) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_BASE_URL}/health", timeout=5.0)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_check_grant_allow_over_real_http(self, _running_gateway: None) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE_URL}/v1/check_grant",
                json={"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
                timeout=5.0,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "allow"

    async def test_check_grant_deny_over_real_http(self, _running_gateway: None) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE_URL}/v1/check_grant",
                json={
                    "agent_id": "presidium://acme.com/researcher",
                    "action": "skill_run:pdf-extract",
                },
                timeout=5.0,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "deny"
        assert body["reason"] == "No matching grant"

    async def test_check_grant_unresolvable_agent_denies_via_real_http(
        self, _running_gateway: None
    ) -> None:
        """FR-1.2: never a 5xx, never an exception -- a real 200 with a deny
        decision, confirmed over the real wire, not just in-process."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BASE_URL}/v1/check_grant",
                json={"agent_id": "presidium://acme.com/ghost", "action": "code_mode"},
                timeout=5.0,
            )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "deny"

    async def test_topology_routes_not_exposed(self, _running_gateway: None) -> None:
        """FR-4.2: this gateway deliberately does not auto-register
        Civitas's own topology introspection routes."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_BASE_URL}/topology", timeout=5.0)
        assert resp.status_code == 404

    async def test_docs_not_exposed(self, _running_gateway: None) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_BASE_URL}/docs", timeout=5.0)
        assert resp.status_code == 404
