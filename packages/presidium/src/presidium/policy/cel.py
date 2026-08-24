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


_UNMATCHED_REASON = "No policy rule matched this request (fail-closed default -- no implicit allow)"


class CelPolicyEngine:
    """Default PolicyEngine using cel-python for in-process evaluation.

    Compile-once, evaluate-many. CEL expressions are compiled at load time.
    Fail-closed: evaluation errors produce DENY with HARD enforcement.

    **Real, deliberate default-deny, 2026-08-24** -- when no rule's expression matches for a
    stage, the engine now denies by default, not allows. See `docs/design/policy-engine.md`'s
    "Design Decisions" P5 for the full reasoning behind this flip (a real, empirical finding:
    every existing policy set relied on the old implicit-ALLOW fallback as an unwritten
    "cleared enforce-grants, no more objections -> allow" terminal step -- the exact
    default-allow anti-pattern this design originally meant to avoid, one level removed).

    Two real, explicit, opt-in knobs for deployments that need something other than the new
    hard default -- named to be easy to grep for in a security review, matching this codebase's
    own established `allow_ungoverned`/`allow_unsandboxed` naming convention, not a neutral,
    equally-weighted enum:

    - ``allow_unmatched_requests`` (default ``False``): set ``True`` to restore the old
      always-ALLOW-on-no-match behavior outright. A real, loud opt-out, not a quiet default.
    - ``unmatched_enforcement`` (default ``EnforcementMode.HARD``): lets a migrating deployment
      keep the new DENY *decision* (so it shows up in real audit logs) while running in
      ``ADVISORY`` mode first -- logged, not actually blocking -- to see the real blast radius
      before committing to ``HARD``. Only meaningful when ``allow_unmatched_requests`` is
      ``False``; ignored otherwise (an ALLOW decision's enforcement mode never blocks anything).
    """

    def __init__(
        self,
        *,
        allow_unmatched_requests: bool = False,
        unmatched_enforcement: EnforcementMode = EnforcementMode.HARD,
    ) -> None:
        self._env = celpy.Environment()
        self._rules_by_stage: dict[EvaluationStage, list[_CompiledRule]] = {}
        self._allow_unmatched_requests = allow_unmatched_requests
        self._unmatched_enforcement = unmatched_enforcement

    def load_policies(self, rules: list[PolicyRule]) -> None:
        new_rules: dict[EvaluationStage, list[_CompiledRule]] = {}

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
                new_rules.setdefault(stage, [])
                new_rules[stage].append(compiled)

        for stage_rules in new_rules.values():
            stage_rules.sort(key=lambda c: c.rule.priority, reverse=True)

        self._rules_by_stage = new_rules

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

        data: dict[str, Any] = {
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
            "result": context.result or {},
        }

        return celpy.json_to_cel(data)  # type: ignore[attr-defined]

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

        if self._allow_unmatched_requests:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                policy_name=None,
                reason="All policies passed",
            )

        return PolicyResult(
            decision=PolicyDecision.DENY,
            policy_name=None,
            reason=_UNMATCHED_REASON,
            enforcement=self._unmatched_enforcement,
        )
