"""GenServer wrapper for AgentRegistry — distributed agent identity store."""

from __future__ import annotations

from typing import Any

from civitas.genserver import GenServer

from presidium.model import AgentRecord, AgentStatus, Grant
from presidium.registry.memory import InMemoryRegistry


class RegistryServer(GenServer):
    """Exposes InMemoryRegistry as a Civitas GenServer for distributed lookups.

    Call protocol:
        {"action": "lookup", "name": "agent-name"}
        → {"found": true, "agent": {...}} | {"found": false}

        {"action": "register", "agent": {...}}
        → {"registered": true, "agent_id": "presidium://..."}

        {"action": "list"}
        → {"agents": [...]}
    """

    def __init__(self, name: str = "presidium.registry", **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._agent_registry = InMemoryRegistry()

    async def init(self) -> None:
        pass

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        action = payload.get("action", "")

        if action == "lookup":
            return await self._handle_lookup(payload)

        if action == "register":
            return await self._handle_register(payload)

        if action == "list":
            return await self._handle_list()

        return {"error": f"Unknown action: {action}"}

    async def _handle_lookup(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload["name"]
        record = await self._agent_registry.lookup(name)
        if record is None:
            return {"found": False}
        return {
            "found": True,
            "agent": {
                "agent_id": record.agent_id,
                "name": record.name,
                "owner": record.owner,
                "status": record.status.value,
                "trust_value": record.trust_value,
                "trust_tier": record.trust_tier.value,
            },
        }

    async def _handle_register(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_data = payload["agent"]
        grants = [
            Grant(
                resources=g.get("resources", []),
                actions=g.get("actions", []),
            )
            for g in agent_data.get("grants", [])
        ]
        record = AgentRecord(
            agent_id=agent_data.get("agent_id", f"presidium://local/{agent_data['name']}"),
            name=agent_data["name"],
            public_key=agent_data.get("public_key", ""),
            owner=agent_data.get("owner"),
            grants=grants,
            status=AgentStatus(agent_data.get("status", "registered")),
        )
        await self._agent_registry.register(record)
        return {"registered": True, "agent_id": record.agent_id}

    async def _handle_list(self) -> dict[str, Any]:
        agents = await self._agent_registry.list_agents()
        return {
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "name": a.name,
                    "status": a.status.value,
                }
                for a in agents
            ]
        }
