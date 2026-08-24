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
    AgentRecord,
    ApprovalRequest,
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    PolicyDecision,
    PolicyResult,
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

    async def _evaluate(
        self, agent_name: str, resource: str, action: str
    ) -> tuple[PolicyResult, AgentRecord | None]:
        """Shared lookup + PRE_TOOL evaluation + audit emission.

        Takes a fully-built ``resource`` string -- callers each construct
        their own resource-naming convention before calling this (``check()``
        prefixes with ``"tool:"``; ``check_grant()`` does not, per
        presidium-server-requirements.md's FR-1.3 "Option 2, refined": the
        whole caller-supplied action string, verbatim). This resolves a real
        naming mismatch found during implementation -- an earlier version of
        this method took a ``tool`` parameter and always prefixed it, which
        silently broke ``check_grant()``'s own "verbatim" requirement.

        Never raises. Returns (PolicyResult(DENY, reason="Agent not found in
        registry"), None) for an unresolvable agent_name -- no audit event is
        emitted in that case (there is no valid AgentRecord to attribute it
        to). ``check()`` and ``check_grant()`` both build on this one
        implementation so they can never drift on lookup/evaluation/audit
        semantics -- only on what they each do with the result afterward.
        """
        record = await self._registry.lookup(agent_name)
        if record is None:
            return (
                PolicyResult(
                    decision=PolicyDecision.DENY,
                    policy_name=None,
                    reason="Agent not found in registry",
                ),
                None,
            )

        context = EvaluationContext(
            agent=record,
            request=ActionRequest(resource=resource, action=action),
            time=datetime.now(UTC),
        )
        result = await self._engine.evaluate(EvaluationStage.PRE_TOOL, context)
        await self._emit_audit(result, context)
        return result, record

    async def check_grant(
        self, agent_name: str, resource: str, action: str = "invoke"
    ) -> PolicyResult:
        """Like check(), but never blocks on approval and never raises.

        ``resource`` is used exactly as given -- NOT prefixed with
        ``"tool:"`` the way ``check()``'s ``tool`` parameter is. Callers
        construct whatever resource-naming convention fits their own domain
        (Presidium Server's ``check_grant`` HTTP endpoint passes the calling
        system's whole action string verbatim, per FR-1.3).

        REQUIRE_APPROVAL decisions are returned as a plain PolicyResult value
        -- not resolved synchronously via ApprovalService -- for callers with
        their own suspend/resume mechanism (e.g. Civitas's durable
        suspension, which is how civitas-io/fabrica's PresidiumClient uses
        this). DENY and an unresolvable agent_name are likewise returned as
        values, never raised -- a caller building an HTTP response (or any
        other fail-closed-as-a-return-value contract) never needs a
        try/except here.
        """
        result, _record = await self._evaluate(agent_name, resource, action)
        return result

    async def check(self, agent_name: str, tool: str, action: str = "invoke") -> Any:
        """Evaluate PRE_TOOL policies for a tool target. Returns PolicyResult.

        Thin wrapper over check_resource() with the tool: prefix -- see check_resource()'s own
        docstring for the full raise/approval/enforcement-mode behavior this delegates to.
        """
        return await self.check_resource(agent_name, f"tool:{tool}", action)

    async def check_resource(self, agent_name: str, resource: str, action: str = "invoke") -> Any:
        """Evaluate PRE_TOOL policies against a resource string used verbatim (no tool: prefix).

        Real reuse point, not a duplicate of check(): lets a caller outside the tool: namespace
        (e.g. GatewayToolProvider.delegate_to_agent()'s agent:<name> resource, per
        mcp-gateway.md's "Design decisions, 2026-08-24") get the exact same raise-on-deny/
        require-approval/enforcement-mode handling check() gives tool: resources, without
        reaching into a private method or duplicating this logic. check() itself is now just
        this method plus the tool: prefix.

        Raises PolicyDeniedError on DENY, an unresolvable agent_name, or a denied
        REQUIRE_APPROVAL. Returns the PolicyResult on ALLOW, ADVISORY, or SOFT.
        """
        result, record = await self._evaluate(agent_name, resource, action)
        if record is None:
            raise PolicyDeniedError(result.reason, result.policy_name)

        if result.enforcement == EnforcementMode.ADVISORY:
            if result.decision != PolicyDecision.ALLOW:
                logger.info(
                    "policy.advisory agent=%s resource=%s decision=%s policy=%s",
                    agent_name,
                    resource,
                    result.decision.value,
                    result.policy_name,
                )
            return result

        if result.enforcement == EnforcementMode.SOFT:
            if result.decision != PolicyDecision.ALLOW:
                logger.warning(
                    "policy.soft agent=%s resource=%s decision=%s policy=%s",
                    agent_name,
                    resource,
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
                request_id=f"tool-{agent_name}-{resource}-{datetime.now(UTC).isoformat()}",
                agent_id=record.agent_id,
                resource=resource,
                action=action,
                reason=result.reason or "Approval required",
                approvers=result.approvers or [],
                context={"resource": resource},
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
        tool: str,
        action: str,
        result_data: dict[str, Any],
    ) -> Any:
        """Evaluate POST_TOOL policies for a tool target. Returns PolicyResult.

        Thin wrapper over post_check_resource() with the tool: prefix, mirroring check()'s own
        split into check_resource().
        """
        return await self.post_check_resource(agent_name, f"tool:{tool}", action, result_data)

    async def post_check_resource(
        self,
        agent_name: str,
        resource: str,
        action: str,
        result_data: dict[str, Any],
    ) -> Any:
        """Evaluate POST_TOOL policies against a resource string used verbatim (no tool: prefix).

        Real reuse point for GatewayToolProvider.delegate_to_agent()'s agent:<name> resource --
        without this, post_check()'s own internal f"tool:{tool}" prefixing would have silently
        produced a double-prefixed "tool:agent:<name>" resource for the POST_TOOL evaluation,
        a real bug caught before it shipped, not after.
        """
        record = await self._registry.lookup(agent_name)
        if record is None:
            raise PolicyDeniedError("Agent not found in registry", None)

        context = EvaluationContext(
            agent=record,
            request=ActionRequest(resource=resource, action=action),
            time=datetime.now(UTC),
            result=result_data,
        )
        post_result = await self._engine.evaluate(EvaluationStage.POST_TOOL, context)
        await self._emit_audit(post_result, context)

        if post_result.enforcement in (EnforcementMode.ADVISORY, EnforcementMode.SOFT):
            return post_result

        if post_result.decision == PolicyDecision.DENY:
            raise PolicyDeniedError(post_result.reason, post_result.policy_name)

        return post_result
