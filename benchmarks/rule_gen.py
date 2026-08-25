"""Shared synthetic rule generation for both the isolated CEL microbenchmark
(cel_microbench.py) and the real HTTP server (serve_m7.py) -- one place, so
the two layers benchmark the *same* rule shape and are actually comparable to
each other, not accidentally different workloads.

Shape: N-1 "distractor" rules that never match the benchmark's own fixed
request, each at a unique, higher priority than the terminal rule -- forcing
first-match-wins to scan every distractor before reaching the terminal ALLOW.
This reproduces docs/vision/roadmap.md's M8 section's own stated worst case:
"a request that matches no rule (the common ALLOW case) evaluates every
loaded rule for that stage."
"""

from __future__ import annotations

from presidium.model import EvaluationStage, PolicyDecision, PolicyRule

BENCHMARK_RESOURCE = "tool:benchmark-target"
BENCHMARK_ACTION = "invoke"


def make_rules(count: int) -> list[PolicyRule]:
    """`count` total rules: `count - 1` distractors (never match) + 1 terminal
    ALLOW at priority 0. `count` must be >= 1.
    """
    if count < 1:
        raise ValueError("count must be >= 1")

    rules: list[PolicyRule] = []
    for i in range(count - 1):
        rules.append(
            PolicyRule(
                name=f"distractor-{i}",
                stage=EvaluationStage.PRE_TOOL,
                expression=f'request.resource == "tool:never-matches-{i}"',
                decision=PolicyDecision.DENY,
                reason="Distractor -- never matches the benchmark request",
                priority=count - i,  # unique, all higher than the terminal rule
            )
        )
    rules.append(
        PolicyRule(
            name="terminal-allow",
            stage=EvaluationStage.PRE_TOOL,
            expression="true",
            decision=PolicyDecision.ALLOW,
            reason="Benchmark terminal rule",
            priority=0,
        )
    )
    return rules
