"""GovernedToolProvider — policy-enforced tool access."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from presidium.approval import ApprovalService
from presidium.audit import AuditEvent, AuditSink
from presidium.errors import PolicyDeniedError
from presidium.model import (
    ActionRequest,
    ApprovalRequest,
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    PolicyDecision,
)
from presidium.policy._base import PolicyEngine
from presidium.registry._base import AgentRegistry

logger = logging.getLogger(__name__)


class GovernedToolProvider:
    """Wraps a tool call function with PRE_TOOL policy enforcement.

    Same three-decision flow as GovernedModelProvider: ALLOW → delegate,
    DENY → raise PolicyDeniedError, REQUIRE_APPROVAL → route to ApprovalService.
    """

    def __init__(
        self,
        engine: PolicyEngine,
        registry: AgentRegistry,
        approval: ApprovalService | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._approval = approval
        self._audit_sink = audit_sink

    async def _emit_audit(self, result: Any, context: EvaluationContext) -> None:
        if self._audit_sink is None:
            return
        event: AuditEvent = {
            "event": "policy.evaluated",
            "ts": datetime.now(UTC).isoformat(),
            "agent": context.agent.name,
            "signer_id": context.agent.name,
            "details": {
                "stage": "pre_tool",
                "resource": context.request.resource,
                "action": context.request.action,
                "decision": result.decision.value,
                "policy_name": result.policy_name,
                "enforcement": result.enforcement.value,
            },
        }
        await self._audit_sink.emit(event)

    async def check(self, agent_name: str, tool: str, action: str = "invoke") -> Any:
        """Evaluate PRE_TOOL policies. Returns PolicyResult."""
        record = await self._registry.lookup(agent_name)
        if record is None:
            raise PolicyDeniedError("Agent not found in registry", None)

        context = EvaluationContext(
            agent=record,
            request=ActionRequest(resource=f"tool:{tool}", action=action),
            time=datetime.now(UTC),
        )
        result = await self._engine.evaluate(EvaluationStage.PRE_TOOL, context)
        await self._emit_audit(result, context)

        if result.enforcement == EnforcementMode.ADVISORY:
            if result.decision != PolicyDecision.ALLOW:
                logger.info(
                    "policy.advisory agent=%s tool=%s decision=%s policy=%s",
                    agent_name,
                    tool,
                    result.decision.value,
                    result.policy_name,
                )
            return result

        if result.enforcement == EnforcementMode.SOFT:
            if result.decision != PolicyDecision.ALLOW:
                logger.warning(
                    "policy.soft agent=%s tool=%s decision=%s policy=%s",
                    agent_name,
                    tool,
                    result.decision.value,
                    result.policy_name,
                )
            return result

        if result.decision == PolicyDecision.DENY:
            raise PolicyDeniedError(result.reason, result.policy_name)

        if result.decision == PolicyDecision.REQUIRE_APPROVAL:
            if self._approval is None:
                raise PolicyDeniedError(
                    "Approval required but no ApprovalService configured",
                    result.policy_name,
                )
            approval_request = ApprovalRequest(
                request_id=f"tool-{agent_name}-{tool}-{datetime.now(UTC).isoformat()}",
                agent_id=record.agent_id,
                resource=f"tool:{tool}",
                action=action,
                reason=result.reason or "Approval required",
                approvers=result.approvers or [],
                context={"tool": tool},
                policy_name=result.policy_name or "",
            )
            decision = await self._approval.request_approval(approval_request)
            if not decision.approved:
                raise PolicyDeniedError(
                    f"Approval denied: {decision.reason}",
                    result.policy_name,
                )

        return result
