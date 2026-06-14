"""GovernedModelProvider — policy-enforced LLM access."""

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


class GovernedModelProvider:
    """Wraps an LLM call function with PRE_LLM policy enforcement.

    Evaluates policies before delegating. ALLOW → delegate,
    DENY → raise PolicyDeniedError, REQUIRE_APPROVAL → route to ApprovalService.
    Advisory and soft modes log but do not block.
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
                "stage": "pre_llm",
                "resource": context.request.resource,
                "action": context.request.action,
                "decision": result.decision.value,
                "policy_name": result.policy_name,
                "enforcement": result.enforcement.value,
            },
        }
        await self._audit_sink.emit(event)

    async def check(self, agent_name: str, model: str) -> Any:
        """Evaluate PRE_LLM policies. Returns PolicyResult."""
        record = await self._registry.lookup(agent_name)
        if record is None:
            raise PolicyDeniedError("Agent not found in registry", None)

        context = EvaluationContext(
            agent=record,
            request=ActionRequest(resource=f"llm:{model}", action="invoke"),
            time=datetime.now(UTC),
        )
        result = await self._engine.evaluate(EvaluationStage.PRE_LLM, context)
        await self._emit_audit(result, context)

        if result.enforcement == EnforcementMode.ADVISORY:
            if result.decision != PolicyDecision.ALLOW:
                logger.info(
                    "policy.advisory agent=%s model=%s decision=%s policy=%s",
                    agent_name,
                    model,
                    result.decision.value,
                    result.policy_name,
                )
            return result

        if result.enforcement == EnforcementMode.SOFT:
            if result.decision != PolicyDecision.ALLOW:
                logger.warning(
                    "policy.soft agent=%s model=%s decision=%s policy=%s",
                    agent_name,
                    model,
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
                request_id=f"llm-{agent_name}-{model}-{datetime.now(UTC).isoformat()}",
                agent_id=record.agent_id,
                resource=f"llm:{model}",
                action="invoke",
                reason=result.reason or "Approval required",
                approvers=result.approvers or [],
                context={"model": model},
                policy_name=result.policy_name or "",
            )
            decision = await self._approval.request_approval(approval_request)
            if not decision.approved:
                raise PolicyDeniedError(
                    f"Approval denied: {decision.reason}",
                    result.policy_name,
                )

        return result

    async def post_check(
        self,
        agent_name: str,
        model: str,
        result_data: dict[str, Any],
    ) -> Any:
        """Evaluate POST_LLM policies against LLM response. Returns PolicyResult."""
        record = await self._registry.lookup(agent_name)
        if record is None:
            raise PolicyDeniedError("Agent not found in registry", None)

        context = EvaluationContext(
            agent=record,
            request=ActionRequest(resource=f"llm:{model}", action="invoke"),
            time=datetime.now(UTC),
            result=result_data,
        )
        post_result = await self._engine.evaluate(EvaluationStage.POST_LLM, context)
        await self._emit_audit(post_result, context)

        if post_result.enforcement in (EnforcementMode.ADVISORY, EnforcementMode.SOFT):
            return post_result

        if post_result.decision == PolicyDecision.DENY:
            raise PolicyDeniedError(post_result.reason, post_result.policy_name)

        return post_result
