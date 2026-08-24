"""Shared policy-rule fixtures used across multiple test files -- not a
conftest.py (these are plain constants, not pytest fixtures; importing
directly from a conftest module isn't this codebase's existing convention).
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
        "flip (docs/design/policy-engine.md P5). A real deployment adds a rule exactly like "
        "this (or something more scoped) once it has finished migrating from the old "
        "implicit-allow fallback -- used here so every test that isn't SPECIFICALLY testing "
        "the new default-deny behavior itself keeps its original, real "
        "allow-when-nothing-else-fires shape without silently reaching for "
        "allow_unmatched_requests=True (which would defeat the point for tests that are meant "
        "to exercise the real, intended production pattern)."
    ),
    priority=0,
)
