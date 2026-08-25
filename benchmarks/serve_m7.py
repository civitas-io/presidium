#!/usr/bin/env python3
"""Boots a real, standalone M7 presidium-contrib server -- HTTPGateway +
PresidiumGatewayAgent + HealthCheckAgent, a real civitas.Runtime/Supervisor --
with a configurable rule-set size, for real external load-generator benchmarks
(ab, k6). Not a pytest fixture: a real, long-running process.

Registers one real agent (`bench-agent`) with a grant matching the benchmark
request shape in rule_gen.py, so the same distractor-rule-scan worst case the
isolated cel_microbench.py measures is what a real check_grant HTTP request
exercises too -- both layers benchmark the identical rule shape.

Usage:
    uv run --package presidium python benchmarks/serve_m7.py --port 8080 --rules 20 --no-mtls
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from civitas import Runtime, Supervisor  # noqa: E402
from civitas.gateway import HTTPGateway  # noqa: E402
from presidium.model import AgentRecord, Grant  # noqa: E402
from presidium.policy.cel import CelPolicyEngine  # noqa: E402
from presidium.registry.memory import InMemoryRegistry  # noqa: E402
from presidium.runtime import GovernedRuntime  # noqa: E402
from presidium_contrib.server import (  # noqa: E402
    HealthCheckAgent,
    PresidiumGatewayAgent,
    build_check_grant_gateway_config,
    build_rate_limiter,
)
from rule_gen import BENCHMARK_ACTION, BENCHMARK_RESOURCE, make_rules  # noqa: E402

_AGENT_ID = "presidium://bench/bench-agent"
_AGENT_NAME = "bench-agent"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--rules", type=int, default=20)
    parser.add_argument("--no-mtls", action="store_true", help="Plaintext HTTP (dev mode).")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--tls-ca-cert")
    parser.add_argument(
        "--rate-limit", type=int, default=0, help="Max requests/window if > 0 (else disabled)."
    )
    args = parser.parse_args()

    registry = InMemoryRegistry()
    await registry.register(
        AgentRecord(
            agent_id=_AGENT_ID,
            name=_AGENT_NAME,
            public_key="",
            grants=[Grant(resources=[BENCHMARK_RESOURCE], actions=[BENCHMARK_ACTION], id="g1")],
        )
    )
    engine = CelPolicyEngine()
    engine.load_policies(make_rules(args.rules))
    runtime = GovernedRuntime(registry=registry, engine=engine)

    gateway_config = build_check_grant_gateway_config(
        host=args.host,
        port=args.port,
        require_mtls=not args.no_mtls,
        tls_cert=args.tls_cert,
        tls_key=args.tls_key,
        tls_ca_cert=args.tls_ca_cert,
        rate_limit=args.rate_limit > 0,
    )
    gateway = HTTPGateway("api", config=gateway_config)
    gateway_agent = PresidiumGatewayAgent(runtime=runtime)
    health_agent = HealthCheckAgent()

    children: list[object] = [gateway, gateway_agent, health_agent]
    if args.rate_limit > 0:
        children.append(build_rate_limiter(args.rate_limit, 60.0))

    supervisor = Supervisor("root", children=children)  # type: ignore[arg-type]
    civitas_runtime = Runtime(supervisor=supervisor)

    print(
        f"presidium M7 benchmark server: {'https' if not args.no_mtls else 'http'}://"
        f"{args.host}:{args.port} -- {args.rules} rules loaded, "
        f"agent={_AGENT_NAME}, resource={BENCHMARK_RESOURCE}, action={BENCHMARK_ACTION}"
    )
    # FR-1.3: the HTTP payload's own "action" field becomes CEL's `request.resource`
    # verbatim (check_grant()'s internal `action` is always the fixed verb "invoke") --
    # the sample body below reflects that real mapping, not the CEL-rule-side naming.
    print(f'sample body: {{"agent_id": "{_AGENT_ID}", "action": "{BENCHMARK_RESOURCE}"}}')
    await civitas_runtime.start()
    try:
        await asyncio.Event().wait()  # run forever
    finally:
        await civitas_runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
