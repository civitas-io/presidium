"""OPAPolicyEngine — wraps OPA REST API for policy evaluation."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from presidium.model import (
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    PolicyDecision,
    PolicyResult,
    PolicyRule,
)

logger = logging.getLogger(__name__)

_STAGE_TO_PATH: dict[EvaluationStage, str] = {
    EvaluationStage.PRE_TOOL: "presidium/pre_tool",
    EvaluationStage.PRE_LLM: "presidium/pre_llm",
    EvaluationStage.REGISTRATION: "presidium/registration",
    EvaluationStage.POST_TOOL: "presidium/post_tool",
    EvaluationStage.POST_LLM: "presidium/post_llm",
}


class OPAPolicyEngine:
    """PolicyEngine adapter that delegates evaluation to an OPA server.

    Sends the full EvaluationContext as JSON input to OPA's Data API.
    Each evaluation stage maps to an OPA policy package path
    (e.g. ``presidium/pre_tool``). The OPA policy must return a JSON
    object with ``decision``, ``reason``, and optionally ``policy_name``,
    ``approvers``, and ``enforcement``.

    ``load_policies`` is a no-op — policies are managed in OPA directly
    (via OPA bundles, the OPA REST API, or filesystem).

    Fail-closed: OPA errors produce DENY with HARD enforcement.
    """

    def __init__(
        self,
        opa_url: str = "http://localhost:8181",
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._opa_url = opa_url.rstrip("/")
        self._headers = headers or {}
        self._timeout = timeout

    def load_policies(self, rules: list[PolicyRule]) -> None:
        pass

    def _build_input(self, stage: EvaluationStage, context: EvaluationContext) -> dict[str, Any]:
        return {
            "input": {
                "stage": stage.value,
                "agent": {
                    "name": context.agent.name,
                    "agent_id": context.agent.agent_id,
                    "owner": context.agent.owner or "",
                    "status": context.agent.status.value,
                    "trust_value": context.agent.trust_value,
                    "trust_tier": context.agent.trust_tier.value,
                    "grants": [
                        {
                            "resources": g.resources,
                            "actions": g.actions,
                            "scope": g.scope,
                        }
                        for g in context.agent.grants
                    ],
                },
                "request": {
                    "resource": context.request.resource,
                    "action": context.request.action,
                    "parameters": context.request.parameters,
                },
                "time": context.time.isoformat(),
                "result": context.result or {},
            }
        }

    async def evaluate(
        self,
        stage: EvaluationStage,
        context: EvaluationContext,
    ) -> PolicyResult:
        path = _STAGE_TO_PATH.get(stage, f"presidium/{stage.value}")
        url = f"{self._opa_url}/v1/data/{path}"
        body = self._build_input(stage, context)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers=self._headers,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("OPA evaluation error — fail-closed DENY: %s", exc)
            return PolicyResult(
                decision=PolicyDecision.DENY,
                policy_name=None,
                reason=f"OPA evaluation error (fail-closed): {exc}",
                enforcement=EnforcementMode.HARD,
            )

        opa_result = data.get("result", {})
        if not opa_result:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                policy_name=None,
                reason="OPA returned no result (default allow)",
            )

        decision_str = opa_result.get("decision", "allow")
        try:
            decision = PolicyDecision(decision_str)
        except ValueError:
            decision = PolicyDecision.DENY

        enforcement_str = opa_result.get("enforcement", "hard")
        try:
            enforcement = EnforcementMode(enforcement_str)
        except ValueError:
            enforcement = EnforcementMode.HARD

        return PolicyResult(
            decision=decision,
            policy_name=opa_result.get("policy_name"),
            reason=opa_result.get("reason"),
            approvers=opa_result.get("approvers"),
            enforcement=enforcement,
        )
