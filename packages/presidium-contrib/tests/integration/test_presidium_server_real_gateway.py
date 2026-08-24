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
    build_rate_limiter,
)
from tests.policy_fixtures import ALLOW_ALL

_PORT = 19443
_BASE_URL = f"http://127.0.0.1:{_PORT}"
_RATE_LIMITED_PORT = 19444
_RATE_LIMITED_BASE_URL = f"http://127.0.0.1:{_RATE_LIMITED_PORT}"

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


@pytest.fixture
async def _running_rate_limited_gateway() -> AsyncGenerator[None]:
    """A second, separate real gateway (its own port) with rate_limit=True -- proves the real
    civitas.gateway.ratelimit.RateLimiter GenServer + middleware wiring actually rejects
    requests with a real 429 over real HTTP, not just that the config assembles without error.
    """
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

    gateway_config = build_check_grant_gateway_config(
        port=_RATE_LIMITED_PORT, require_mtls=False, rate_limit=True
    )
    gateway = HTTPGateway("api", config=gateway_config)
    gateway_agent = PresidiumGatewayAgent(runtime=runtime)
    health_agent = HealthCheckAgent()
    # Real, small budget -- deliberately low so the test can exhaust it in a handful of
    # requests, not thousands.
    rate_limiter = build_rate_limiter(max_requests=3, window_seconds=60.0)

    supervisor = Supervisor("root", children=[gateway, gateway_agent, health_agent, rate_limiter])
    civitas_runtime = Runtime(supervisor=supervisor)
    await civitas_runtime.start()
    try:
        try:
            await _wait_for_port_open("127.0.0.1", _RATE_LIMITED_PORT)
        except (OSError, TimeoutError):
            pass
        await asyncio.sleep(0.05)
        yield
    finally:
        await civitas_runtime.stop()


class TestPresidiumServerRateLimiting:
    """Real, end-to-end proof that civitas.gateway.ratelimit is correctly wired onto
    /v1/check_grant and correctly NOT wired onto /health -- both halves matter, not just that
    a 429 eventually happens somewhere.
    """

    async def test_check_grant_rejects_over_the_real_budget_with_429(
        self, _running_rate_limited_gateway: None
    ) -> None:
        async with httpx.AsyncClient() as client:
            statuses = []
            for _ in range(5):
                resp = await client.post(
                    f"{_RATE_LIMITED_BASE_URL}/v1/check_grant",
                    json={"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
                    timeout=5.0,
                )
                statuses.append(resp.status_code)

        # Real budget is 3 -- the first 3 real requests succeed, the rest are real 429s.
        assert statuses == [200, 200, 200, 429, 429]

    async def test_429_response_includes_retry_after(
        self, _running_rate_limited_gateway: None
    ) -> None:
        async with httpx.AsyncClient() as client:
            for _ in range(3):
                await client.post(
                    f"{_RATE_LIMITED_BASE_URL}/v1/check_grant",
                    json={"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
                    timeout=5.0,
                )
            resp = await client.post(
                f"{_RATE_LIMITED_BASE_URL}/v1/check_grant",
                json={"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
                timeout=5.0,
            )

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert resp.json() == {"error": "rate limit exceeded"}

    async def test_health_is_never_rate_limited(self, _running_rate_limited_gateway: None) -> None:
        """The real point of putting rate-limit middleware on check_grant's own per-route list,
        not the global config -- a liveness probe must keep working even after check_grant's
        real budget is exhausted."""
        async with httpx.AsyncClient() as client:
            # Exhaust check_grant's real budget first.
            for _ in range(5):
                await client.post(
                    f"{_RATE_LIMITED_BASE_URL}/v1/check_grant",
                    json={"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
                    timeout=5.0,
                )

            health_statuses = []
            for _ in range(5):
                resp = await client.get(f"{_RATE_LIMITED_BASE_URL}/health", timeout=5.0)
                health_statuses.append(resp.status_code)

        assert health_statuses == [200, 200, 200, 200, 200]

    async def test_rate_limit_is_off_by_default(self, _running_gateway: None) -> None:
        """The pre-existing, unrelated _running_gateway fixture (rate_limit not passed at all,
        defaulting to False) -- confirms the default really is off, not silently on."""
        async with httpx.AsyncClient() as client:
            statuses = []
            for _ in range(10):
                resp = await client.post(
                    f"{_BASE_URL}/v1/check_grant",
                    json={"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
                    timeout=5.0,
                )
                statuses.append(resp.status_code)

        assert statuses == [200] * 10
