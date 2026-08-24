"""Presidium Server (M7) — a real, self-hostable network governance service.

See docs/design/presidium-server-requirements.md and presidium-server.md in
the repo root for the full design. `presidium_contrib.server` requires the
`presidium-contrib[server]` extra (`civitas[http]` + `cryptography`).
"""

from presidium_contrib.server.gateway_agent import (
    RATE_LIMITER_AGENT_NAME,
    HealthCheckAgent,
    PresidiumGatewayAgent,
    build_check_grant_gateway_config,
    build_rate_limiter,
)

__all__ = [
    "RATE_LIMITER_AGENT_NAME",
    "HealthCheckAgent",
    "PresidiumGatewayAgent",
    "build_check_grant_gateway_config",
    "build_rate_limiter",
]
