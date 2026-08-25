#!/usr/bin/env python3
"""End-to-end GovernedMcpToolPipeline.call_tool() benchmark -- the REAL,
composed cost (poisoning check -> redact arguments -> PRE_TOOL CEL ->
backend call -> PII scan -> POST_TOOL CEL -> optional PII mask), not just
the individual primitives in isolation (see mcp_governance_microbench.py).
A small, fixed CEL rule set is used deliberately -- CEL's own rule-count
scaling is already benchmarked separately (cel_microbench.py); this script
isolates the effect of tool-RESULT size on the full pipeline.

Usage:
    uv run --package presidium-contrib python benchmarks/mcp_pipeline_e2e_bench.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from mcp_governance_microbench import _make_payload  # noqa: E402
from presidium.model import (  # noqa: E402
    AgentRecord,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine  # noqa: E402
from presidium.providers.tool import GovernedToolProvider  # noqa: E402
from presidium.registry.memory import InMemoryRegistry  # noqa: E402
from presidium_contrib.mcp_gateway.pii import PIIDetector  # noqa: E402
from presidium_contrib.mcp_gateway.pipeline import GovernedMcpToolPipeline  # noqa: E402

ALLOW_ALL = PolicyRule(
    name="allow-all",
    stage=[EvaluationStage.PRE_TOOL, EvaluationStage.POST_TOOL],
    expression="true",
    decision=PolicyDecision.ALLOW,
    reason="Benchmark allow-all",
    priority=0,
)


class _FakeBackend:
    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result
        self.tools = [{"name": "bench_tool", "description": "Benchmark tool", "input_schema": {}}]

    async def list_tools(self, *, agent_name: str | None = None) -> list[dict[str, Any]]:
        return self.tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, agent_name: str | None = None
    ) -> dict[str, Any]:
        return dict(self._result)

    async def health(self) -> bool:
        return True


async def _setup(result_size: int) -> GovernedMcpToolPipeline:
    registry = InMemoryRegistry()
    await registry.register(
        AgentRecord(
            agent_id="presidium://bench/agent",
            name="bench-agent",
            public_key="",
            trust_value=0.5,
            trust_tier=TrustTier.STANDARD,
            grants=[Grant(resources=["bench_tool"], actions=["invoke"], id="g1")],
        )
    )
    engine = CelPolicyEngine()
    engine.load_policies([ALLOW_ALL])
    tool_provider = GovernedToolProvider(engine, registry)
    backend = _FakeBackend(_make_payload(result_size))
    pipeline = GovernedMcpToolPipeline(
        backend=backend,  # type: ignore[arg-type]
        tool_provider=tool_provider,
        agent_name="bench-agent",
        pii_detector=PIIDetector(),
    )
    pipeline.approve_tool("bench_tool", "Benchmark tool", {}, approved_by="bench")
    return pipeline


async def _bench_one(result_size: int, iterations: int) -> dict[str, float]:
    pipeline = await _setup(result_size)
    samples_us: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await pipeline.call_tool(
            "bench_tool", {}, tool_description="Benchmark tool", tool_input_schema={}
        )
        samples_us.append((time.perf_counter() - t0) * 1_000_000)
    samples_us.sort()

    def pct(p: float) -> float:
        idx = min(int(len(samples_us) * p), len(samples_us) - 1)
        return samples_us[idx]

    return {
        "mean_us": statistics.mean(samples_us),
        "p50_us": pct(0.50),
        "p95_us": pct(0.95),
        "p99_us": pct(0.99),
    }


async def main() -> None:
    print(f"{'result_size':>12} {'mean_us':>12} {'p50_us':>12} {'p95_us':>12} {'p99_us':>12}")
    for size in (100, 1_000, 10_000, 100_000):
        iterations = max(10, min(500, 500_000 // size))
        r = await _bench_one(size, iterations)
        print(
            f"{size:>12} {r['mean_us']:>12.1f} {r['p50_us']:>12.1f} "
            f"{r['p95_us']:>12.1f} {r['p99_us']:>12.1f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
