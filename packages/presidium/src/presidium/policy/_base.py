"""PolicyEngine Protocol definition."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from presidium.model import EvaluationContext, EvaluationStage, PolicyResult, PolicyRule


@runtime_checkable
class PolicyEngine(Protocol):
    """Protocol for policy evaluation.

    Implementations compile rules at load time and evaluate them
    per-stage against an EvaluationContext. First-match-wins by priority.
    No match → ALLOW.
    """

    def load_policies(self, rules: list[PolicyRule]) -> None:
        """Load and compile policy rules. Raises on invalid expressions."""
        ...

    async def evaluate(
        self,
        stage: EvaluationStage,
        context: EvaluationContext,
    ) -> PolicyResult: ...
