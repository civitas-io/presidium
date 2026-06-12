"""CelPolicyEngine — CEL-based policy evaluation."""

from __future__ import annotations

import logging
from typing import Any

import celpy

from presidium.errors import PolicyCompilationError
from presidium.model import (
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    PolicyDecision,
    PolicyResult,
    PolicyRule,
)

logger = logging.getLogger(__name__)


class _CompiledRule:
    __slots__ = ("rule", "program")

    def __init__(self, rule: PolicyRule, program: celpy.Runner) -> None:
        self.rule = rule
        self.program = program


class CelPolicyEngine:
    """Default PolicyEngine using cel-python for in-process evaluation.

    Compile-once, evaluate-many. CEL expressions are compiled at load time.
    Fail-closed: evaluation errors produce DENY with HARD enforcement.
    """

    def __init__(self) -> None:
        self._env = celpy.Environment()
        self._rules_by_stage: dict[EvaluationStage, list[_CompiledRule]] = {}

    def load_policies(self, rules: list[PolicyRule]) -> None:
        self._rules_by_stage.clear()

        for rule in rules:
            if not rule.enabled:
                continue

            try:
                ast = self._env.compile(rule.expression)
            except celpy.CELParseError as exc:  # type: ignore[attr-defined]
                raise PolicyCompilationError(rule.name, rule.expression, str(exc)) from exc

            program = self._env.program(ast)
            compiled = _CompiledRule(rule, program)

            stages: list[EvaluationStage]
            if isinstance(rule.stage, list):
                stages = rule.stage
            else:
                stages = [rule.stage]

            for stage in stages:
                self._rules_by_stage.setdefault(stage, [])
                self._rules_by_stage[stage].append(compiled)

        for stage_rules in self._rules_by_stage.values():
            stage_rules.sort(key=lambda c: c.rule.priority, reverse=True)

    def _build_activation(self, context: EvaluationContext) -> Any:
        now = context.time
        active_grants: list[dict[str, Any]] = []
        for g in context.agent.grants:
            if g.expires_at is not None and g.expires_at < now:
                continue
            active_grants.append(
                {
                    "resources": g.resources,
                    "actions": g.actions,
                    "scope": g.scope,
                    "condition": g.condition or "",
                }
            )

        return celpy.json_to_cel(  # type: ignore[attr-defined]
            {
                "agent": {
                    "name": context.agent.name,
                    "agent_id": context.agent.agent_id,
                    "owner": context.agent.owner or "",
                    "status": context.agent.status.value,
                    "trust": {
                        "value": context.agent.trust_value,
                        "tier": context.agent.trust_tier.value,
                    },
                    "grants": active_grants,
                },
                "request": {
                    "resource": context.request.resource,
                    "action": context.request.action,
                    "parameters": context.request.parameters,
                },
                "time": now.isoformat(),
            }
        )

    async def evaluate(
        self,
        stage: EvaluationStage,
        context: EvaluationContext,
    ) -> PolicyResult:
        compiled_rules = self._rules_by_stage.get(stage, [])

        activation = self._build_activation(context)

        for compiled in compiled_rules:
            rule = compiled.rule
            try:
                result = compiled.program.evaluate(activation)
            except Exception as exc:
                logger.warning(
                    "Policy '%s' evaluation error — fail-closed DENY: %s",
                    rule.name,
                    exc,
                )
                return PolicyResult(
                    decision=PolicyDecision.DENY,
                    policy_name=rule.name,
                    reason=f"Policy evaluation error (fail-closed): {exc}",
                    enforcement=EnforcementMode.HARD,
                )

            if str(result) == "True":
                return PolicyResult(
                    decision=rule.decision,
                    policy_name=rule.name,
                    reason=rule.reason,
                    approvers=list(rule.approvers) if rule.approvers else None,
                    enforcement=rule.enforcement,
                )

        return PolicyResult(
            decision=PolicyDecision.ALLOW,
            policy_name=None,
            reason="All policies passed",
        )
