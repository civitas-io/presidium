"""Real tests for RegistryServer — previously 0% covered.

Exercises `handle_call()` directly for fast, focused coverage of every
branch. See `tests/integration/test_service_mode_real_runtime.py` for the
real end-to-end test through an actual Civitas Runtime/Supervisor, which
also regression-tests the `self._registry` / `AgentProcess._registry`
attribute-name collision fixed alongside this test suite.
"""

from __future__ import annotations

from presidium_contrib.service.registry import RegistryServer


def _agent_payload(name: str = "researcher", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "owner": "alice@acme.com",
        "grants": [{"resources": ["tool:database"], "actions": ["read"]}],
    }
    payload.update(overrides)
    return payload


class TestHandleCallRegister:
    async def test_register_returns_registered_true_and_agent_id(self) -> None:
        server = RegistryServer()
        result = await server.handle_call(
            {"action": "register", "agent": _agent_payload()}, "sender"
        )
        assert result["registered"] is True
        assert result["agent_id"] == "presidium://local/researcher"

    async def test_register_uses_explicit_agent_id_when_given(self) -> None:
        server = RegistryServer()
        result = await server.handle_call(
            {
                "action": "register",
                "agent": _agent_payload(agent_id="presidium://acme.com/researcher"),
            },
            "sender",
        )
        assert result["agent_id"] == "presidium://acme.com/researcher"

    async def test_register_persists_grants(self) -> None:
        server = RegistryServer()
        await server.handle_call({"action": "register", "agent": _agent_payload()}, "sender")

        record = await server._agent_registry.lookup("researcher")
        assert record is not None
        assert len(record.grants) == 1
        assert record.grants[0].resources == ["tool:database"]


class TestHandleCallLookup:
    async def test_lookup_found(self) -> None:
        server = RegistryServer()
        await server.handle_call({"action": "register", "agent": _agent_payload()}, "sender")

        result = await server.handle_call({"action": "lookup", "name": "researcher"}, "sender")
        assert result["found"] is True
        assert result["agent"]["name"] == "researcher"
        assert result["agent"]["owner"] == "alice@acme.com"
        assert result["agent"]["status"] == "registered"
        assert result["agent"]["trust_tier"] == "standard"

    async def test_lookup_not_found(self) -> None:
        server = RegistryServer()
        result = await server.handle_call({"action": "lookup", "name": "ghost"}, "sender")
        assert result["found"] is False


class TestHandleCallList:
    async def test_list_empty(self) -> None:
        server = RegistryServer()
        result = await server.handle_call({"action": "list"}, "sender")
        assert result["agents"] == []

    async def test_list_returns_registered_agents(self) -> None:
        server = RegistryServer()
        await server.handle_call(
            {"action": "register", "agent": _agent_payload("researcher")}, "sender"
        )
        await server.handle_call(
            {"action": "register", "agent": _agent_payload("writer")}, "sender"
        )

        result = await server.handle_call({"action": "list"}, "sender")
        names = {a["name"] for a in result["agents"]}
        assert names == {"researcher", "writer"}


class TestHandleCallUnknownAction:
    async def test_unknown_action_returns_error(self) -> None:
        server = RegistryServer()
        result = await server.handle_call({"action": "nonexistent"}, "sender")
        assert "error" in result
        assert "nonexistent" in result["error"]

    async def test_missing_action_returns_error(self) -> None:
        server = RegistryServer()
        result = await server.handle_call({}, "sender")
        assert "error" in result
