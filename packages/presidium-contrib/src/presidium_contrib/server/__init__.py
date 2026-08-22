"""Presidium Server (M7) — a real, self-hostable network governance service.

See docs/design/presidium-server-requirements.md and presidium-server.md in
the repo root for the full design. `presidium_contrib.server` requires the
`presidium-contrib[server]` extra (`civitas[http]` + `cryptography`).
"""

from presidium_contrib.server.gateway_agent import (
    HealthCheckAgent,
    PresidiumGatewayAgent,
    build_check_grant_gateway_config,
)

__all__ = ["HealthCheckAgent", "PresidiumGatewayAgent", "build_check_grant_gateway_config"]
