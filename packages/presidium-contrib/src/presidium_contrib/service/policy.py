"""GenServer wrapper for CelPolicyEngine — distributed policy evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from civitas.genserver import GenServer

from presidium.model import (
    ActionRequest,
    AgentRecord,
    AgentStatus,
    EvaluationContext,
    EvaluationStage,
    Grant,
    PolicyRule,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine


class PolicyEvaluatorServer(GenServer):
    """Exposes CelPolicyEngine as a Civitas GenServer for distributed evaluation.

    Call protocol:
        {"action": "evaluate", "stage": "pre_tool", "agent": {...}, "request": {...}}
        → {"decision": "allow", "policy_name": null, "reason": "All policies passed"}

        {"action": "load_policies", "rules": [...]}
        → {"loaded": N}
    """

    def __init__(self, name: str = "presidium.policy", **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._engine = CelPolicyEngine()

    async def init(self) -> None:
        pass

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        action = payload.get("action", "")

        if action == "evaluate":
            return await self._handle_evaluate(payload)

        if action == "load_policies":
            return self._handle_load(payload)

        return {"error": f"Unknown action: {action}"}

    async def _handle_evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        stage = EvaluationStage(payload["stage"])

        agent_data = payload["agent"]
        grants = [
            Grant(
                resources=g.get("resources", []),
                actions=g.get("actions", []),
            )
            for g in agent_data.get("grants", [])
        ]
        agent = AgentRecord(
            agent_id=agent_data.get("agent_id", ""),
            name=agent_data.get("name", ""),
            public_key="",
            owner=agent_data.get("owner"),
            grants=grants,
            trust_value=agent_data.get("trust_value", 0.5),
            trust_tier=TrustTier(agent_data.get("trust_tier", "standard")),
            status=AgentStatus(agent_data.get("status", "running")),
        )

        req_data = payload.get("request", {})
        request = ActionRequest(
            resource=req_data.get("resource", ""),
            action=req_data.get("action", ""),
            parameters=req_data.get("parameters", {}),
        )

        context = EvaluationContext(
            agent=agent,
            request=request,
            time=datetime.now(UTC),
            result=payload.get("result"),
        )

        result = await self._engine.evaluate(stage, context)
        return {
            "decision": result.decision.value,
            "policy_name": result.policy_name,
            "reason": result.reason,
            "enforcement": result.enforcement.value,
        }

    def _handle_load(self, payload: dict[str, Any]) -> dict[str, Any]:
        rules_data = payload.get("rules", [])
        rules: list[PolicyRule] = []
        for r in rules_data:
            stage_raw = r.get("stage", "pre_tool")
            if isinstance(stage_raw, list):
                stage: EvaluationStage | list[EvaluationStage] = [
                    EvaluationStage(s) for s in stage_raw
                ]
            else:
                stage = EvaluationStage(stage_raw)
            rules.append(
                PolicyRule(
                    name=r["name"],
                    stage=stage,
                    expression=r["expression"],
                    decision=r.get("decision", "deny"),
                    reason=r.get("reason"),
                    priority=r.get("priority", 0),
                    enabled=r.get("enabled", True),
                )
            )
        self._engine.load_policies(rules)
        return {"loaded": len(rules)}
