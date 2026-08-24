"""Shared policy-rule fixtures used across multiple presidium-contrib test
files. Mirrors packages/presidium/tests/policy_fixtures.py's own ALLOW_ALL
exactly -- not shared cross-package (presidium-contrib's own test suite
runs against its own separate venv/rootdir; there's no existing precedent
in this codebase for importing test utilities across the two packages).
"""

from __future__ import annotations

from presidium.model import EvaluationStage, PolicyDecision, PolicyRule

ALLOW_ALL = PolicyRule(
    name="allow-all",
    stage=[
        EvaluationStage.PRE_TOOL,
        EvaluationStage.PRE_LLM,
        EvaluationStage.PRE_MESSAGE,
        EvaluationStage.REGISTRATION,
        EvaluationStage.POST_TOOL,
        EvaluationStage.POST_LLM,
    ],
    expression="true",
    decision=PolicyDecision.ALLOW,
    reason=(
        "Explicit terminal allow -- real migration required by the 2026-08-24 default-deny "
        "flip in presidium's CelPolicyEngine (docs/design/policy-engine.md P5, presidium repo). "
        "Used here so tests that aren't SPECIFICALLY about the new default-deny behavior "
        "itself keep their original, real allow-when-nothing-else-fires shape."
    ),
    priority=0,
)
