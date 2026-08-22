"""Real tests for build_check_grant_gateway_config()."""

from __future__ import annotations

from presidium_contrib.server.gateway_agent import (
    DEFAULT_AGENT_NAME,
    DEFAULT_HEALTH_AGENT_NAME,
    build_check_grant_gateway_config,
)


class TestBuildCheckGrantGatewayConfig:
    def test_default_requires_mtls(self) -> None:
        config = build_check_grant_gateway_config(
            tls_cert="/etc/presidium/server.crt",
            tls_key="/etc/presidium/server.key",
            tls_ca_cert="/etc/presidium/ca.crt",
        )
        assert config.client_cert_mode == "required"
        assert "civitas.gateway.mtls.require_client_cert" in config.middleware

    def test_mtls_can_be_disabled_for_local_dev(self) -> None:
        config = build_check_grant_gateway_config(require_mtls=False)
        assert config.client_cert_mode == "none"
        assert config.middleware == []

    def test_routes_are_check_grant_and_health_only(self) -> None:
        """FR-4.2: deliberately not Civitas's full topology introspection surface."""
        config = build_check_grant_gateway_config(require_mtls=False)
        paths = {(r["method"], r["path"]) for r in config.routes}
        assert paths == {("POST", "/v1/check_grant"), ("GET", "/health")}
        assert config.topology_agent is None

    def test_routes_point_at_distinct_agents_by_default(self) -> None:
        """check_grant and health are deliberately two separate agents (see
        gateway_agent.py's own module docstring for why one dispatch-by-
        payload-marker agent doesn't work with Civitas's real route API)."""
        config = build_check_grant_gateway_config(require_mtls=False)
        by_path = {r["path"]: r["agent"] for r in config.routes}
        assert by_path["/v1/check_grant"] == DEFAULT_AGENT_NAME
        assert by_path["/health"] == DEFAULT_HEALTH_AGENT_NAME
        assert by_path["/v1/check_grant"] != by_path["/health"]

    def test_agent_names_are_overridable(self) -> None:
        config = build_check_grant_gateway_config(
            require_mtls=False,
            agent_name="custom.gateway",
            health_agent_name="custom.health",
        )
        by_path = {r["path"]: r["agent"] for r in config.routes}
        assert by_path["/v1/check_grant"] == "custom.gateway"
        assert by_path["/health"] == "custom.health"

    def test_docs_disabled_by_default(self) -> None:
        """A security product's own API: no public Swagger UI by default."""
        config = build_check_grant_gateway_config(require_mtls=False)
        assert config.docs_enabled is False
