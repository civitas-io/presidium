#!/usr/bin/env python3
"""Isolated CelPolicyEngine.evaluate() microbenchmark -- no HTTP, no network,
no registry I/O. Reproduces docs/vision/roadmap.md's M8 baseline (~88us/eval
at 20 rules) as a real, checked-in, reusable script -- no such script existed
before this benchmark pass; the original number was measured ad hoc.

Usage:
    uv run --package presidium python benchmarks/cel_microbench.py --rules 20
    uv run --package presidium python benchmarks/cel_microbench.py \
        --rules 5 --rules 20 --rules 50 --rules 100
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from presidium.model import (  # noqa: E402
    ActionRequest,
    AgentRecord,
    AgentStatus,
    EvaluationContext,
    EvaluationStage,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine  # noqa: E402
from rule_gen import BENCHMARK_ACTION, BENCHMARK_RESOURCE, make_rules  # noqa: E402


async def run_one(rule_count: int, iterations: int) -> dict[str, float]:
    engine = CelPolicyEngine()
    engine.load_policies(make_rules(rule_count))

    agent = AgentRecord(
        agent_id="presidium://bench/agent",
        name="bench-agent",
        public_key="a2V5",
        trust_value=0.5,
        trust_tier=TrustTier.STANDARD,
        status=AgentStatus.RUNNING,
    )
    context = EvaluationContext(
        agent=agent,
        request=ActionRequest(resource=BENCHMARK_RESOURCE, action=BENCHMARK_ACTION),
        time=datetime.now(UTC),
    )

    # Warm-up (JIT-free interpreter, but avoids first-call import/compile-cache noise)
    for _ in range(100):
        await engine.evaluate(EvaluationStage.PRE_TOOL, context)

    samples_us: list[float] = []
    start_wall = time.perf_counter()
    for _ in range(iterations):
        t0 = time.perf_counter()
        result = await engine.evaluate(EvaluationStage.PRE_TOOL, context)
        samples_us.append((time.perf_counter() - t0) * 1_000_000)
    wall_seconds = time.perf_counter() - start_wall

    assert result.decision.value == "allow", f"unexpected decision: {result.decision}"

    samples_us.sort()

    def pct(p: float) -> float:
        idx = min(int(len(samples_us) * p), len(samples_us) - 1)
        return samples_us[idx]

    return {
        "rule_count": rule_count,
        "iterations": iterations,
        "mean_us": statistics.mean(samples_us),
        "p50_us": pct(0.50),
        "p95_us": pct(0.95),
        "p99_us": pct(0.99),
        "evals_per_sec": iterations / wall_seconds,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rules",
        type=int,
        action="append",
        default=None,
        help="Rule-set size to benchmark (repeatable). Default: 5 20 50 100.",
    )
    parser.add_argument("--iterations", type=int, default=20_000)
    args = parser.parse_args()
    rule_counts = args.rules or [5, 20, 50, 100]

    cols = ("rules", "mean_us", "p50_us", "p95_us", "p99_us", "evals/sec")
    widths = (6, 10, 10, 10, 10, 12)
    print(" ".join(f"{c:>{w}}" for c, w in zip(cols, widths, strict=True)))
    for count in rule_counts:
        r = await run_one(count, args.iterations)
        print(
            f"{r['rule_count']:>6} {r['mean_us']:>10.2f} {r['p50_us']:>10.2f} "
            f"{r['p95_us']:>10.2f} {r['p99_us']:>10.2f} {r['evals_per_sec']:>12.0f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
