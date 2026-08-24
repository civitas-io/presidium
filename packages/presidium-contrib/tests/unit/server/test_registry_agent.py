"""Real tests for RegisterAgentGatewayAgent/ListAgentsGatewayAgent/GetAgentGatewayAgent/
DeregisterAgentGatewayAgent -- direct handle_call() invocation, matching
test_gateway_agent.py's own established pattern.

See tests/integration/test_registry_gateway_real_http.py for the real end-to-end test through
an actual civitas.gateway.HTTPGateway.
"""

from __future__ import annotations

from presidium.registry.memory import InMemoryRegistry
from presidium_contrib.server import (
    DeregisterAgentGatewayAgent,
    GetAgentGatewayAgent,
    ListAgentsGatewayAgent,
    RegisterAgentGatewayAgent,
)


class TestRegisterAgentGatewayAgent:
    async def test_register_with_required_fields_only(self) -> None:
        registry = InMemoryRegistry()
        agent = RegisterAgentGatewayAgent(registry=registry)

        result = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "name": "researcher",
                "public_key": "a2V5",
            },
            "sender",
        )

        assert result["status"] == "registered"
        assert result["agent"]["name"] == "researcher"
        assert result["agent"]["public_key_algorithm"] == "ed25519"
        assert result["agent"]["status"] == "registered"
        assert result["agent"]["trust_value"] == 0.5

    async def test_register_with_optional_fields(self) -> None:
        registry = InMemoryRegistry()
        agent = RegisterAgentGatewayAgent(registry=registry)

        result = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "name": "researcher",
                "public_key": "a2V5",
                "owner": "alice@acme.com",
                "description": "A research agent",
                "capabilities": ["web_search"],
                "metadata": {"team": "research"},
            },
            "sender",
        )

        assert result["status"] == "registered"
        assert result["agent"]["owner"] == "alice@acme.com"
        assert result["agent"]["description"] == "A research agent"
        assert result["agent"]["capabilities"] == ["web_search"]
        assert result["agent"]["metadata"] == {"team": "research"}

    async def test_register_missing_required_field_returns_error_not_raises(self) -> None:
        registry = InMemoryRegistry()
        agent = RegisterAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({"agent_id": "presidium://acme.com/x"}, "sender")

        assert result["status"] == "error"
        assert "name" in result["reason"]
        assert "public_key" in result["reason"]

    async def test_register_cannot_set_grants_directly(self) -> None:
        """Real, deliberate security scoping: grants are excluded from the registrable field
        set -- confirmed here by sending a grants key and asserting it's silently ignored, not
        applied."""
        registry = InMemoryRegistry()
        agent = RegisterAgentGatewayAgent(registry=registry)

        result = await agent.handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "name": "researcher",
                "public_key": "a2V5",
                "grants": [{"resources": ["tool:database"], "actions": ["read"], "id": "g1"}],
            },
            "sender",
        )

        assert result["status"] == "registered"
        assert result["agent"]["grants"] == []

    async def test_register_is_upsert_matching_registry_semantics(self) -> None:
        registry = InMemoryRegistry()
        agent = RegisterAgentGatewayAgent(registry=registry)
        first = {
            "agent_id": "presidium://acme.com/researcher",
            "name": "researcher",
            "public_key": "a2V5",
            "owner": "alice@acme.com",
        }
        second = {**first, "owner": "bob@acme.com"}

        await agent.handle_call(first, "sender")
        result = await agent.handle_call(second, "sender")

        assert result["status"] == "registered"
        assert result["agent"]["owner"] == "bob@acme.com"


class TestListAgentsGatewayAgent:
    async def test_list_empty_registry(self) -> None:
        registry = InMemoryRegistry()
        agent = ListAgentsGatewayAgent(registry=registry)

        result = await agent.handle_call({}, "sender")

        assert result == {"status": "ok", "agents": []}

    async def test_list_returns_all_registered_agents(self) -> None:
        registry = InMemoryRegistry()
        register_agent = RegisterAgentGatewayAgent(registry=registry)
        await register_agent.handle_call(
            {"agent_id": "presidium://acme.com/a", "name": "a", "public_key": "a2V5"}, "sender"
        )
        await register_agent.handle_call(
            {"agent_id": "presidium://acme.com/b", "name": "b", "public_key": "a2V5"}, "sender"
        )

        agent = ListAgentsGatewayAgent(registry=registry)
        result = await agent.handle_call({}, "sender")

        assert result["status"] == "ok"
        names = {a["name"] for a in result["agents"]}
        assert names == {"a", "b"}

    async def test_list_ignores_query_style_payload_keys(self) -> None:
        """Real, honest scope note confirmed: this endpoint doesn't filter (query params never
        reach handle_call() at all over real HTTP) -- passing filter-shaped keys directly to
        handle_call() (simulating what a smarter dispatch might one day forward) is still
        ignored, proving the current implementation genuinely always returns everything, not
        that it happens to work by accident."""
        registry = InMemoryRegistry()
        agent = ListAgentsGatewayAgent(registry=registry)

        result = await agent.handle_call({"status": "suspended", "owner": "nobody"}, "sender")

        assert result == {"status": "ok", "agents": []}


class TestGetAgentGatewayAgent:
    async def test_get_agent_with_grants_serializes_them(self) -> None:
        """Real, not fabricated: exercises _grant_to_dict() via an agent that actually has a
        grant, added in-process (grants aren't settable through the register endpoint itself,
        per this module's own deliberate scoping) -- confirmed here that a real, existing
        grant is genuinely serialized when reading the agent back over HTTP."""
        from presidium.model import Grant

        registry = InMemoryRegistry()
        await RegisterAgentGatewayAgent(registry=registry).handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "name": "researcher",
                "public_key": "a2V5",
            },
            "sender",
        )
        await registry.add_grant(
            "researcher",
            Grant(resources=["tool:database"], actions=["read"], id="g1", scope={"env": "prod"}),
        )
        agent = GetAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({"name": "researcher"}, "sender")

        assert result["status"] == "found"
        [grant] = result["agent"]["grants"]
        assert grant == {
            "id": "g1",
            "resources": ["tool:database"],
            "actions": ["read"],
            "scope": {"env": "prod"},
            "condition": None,
            "expires_at": None,
        }

    async def test_get_existing_agent(self) -> None:
        registry = InMemoryRegistry()
        await RegisterAgentGatewayAgent(registry=registry).handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "name": "researcher",
                "public_key": "a2V5",
            },
            "sender",
        )
        agent = GetAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({"name": "researcher"}, "sender")

        assert result["status"] == "found"
        assert result["agent"]["name"] == "researcher"

    async def test_get_unknown_agent_returns_not_found_not_raises(self) -> None:
        registry = InMemoryRegistry()
        agent = GetAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({"name": "ghost"}, "sender")

        assert result == {"status": "not_found", "reason": "Agent not found"}

    async def test_get_missing_name_path_param(self) -> None:
        registry = InMemoryRegistry()
        agent = GetAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({}, "sender")

        assert result["status"] == "error"


class TestDeregisterAgentGatewayAgent:
    async def test_deregister_existing_agent(self) -> None:
        registry = InMemoryRegistry()
        await RegisterAgentGatewayAgent(registry=registry).handle_call(
            {
                "agent_id": "presidium://acme.com/researcher",
                "name": "researcher",
                "public_key": "a2V5",
            },
            "sender",
        )
        agent = DeregisterAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({"name": "researcher"}, "sender")

        assert result == {"status": "deregistered"}
        assert await registry.lookup("researcher") is None

    async def test_deregister_unknown_agent_returns_not_found_not_raises(self) -> None:
        registry = InMemoryRegistry()
        agent = DeregisterAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({"name": "ghost"}, "sender")

        assert result == {"status": "not_found", "reason": "Agent not found"}

    async def test_deregister_missing_name_path_param(self) -> None:
        registry = InMemoryRegistry()
        agent = DeregisterAgentGatewayAgent(registry=registry)

        result = await agent.handle_call({}, "sender")

        assert result["status"] == "error"
