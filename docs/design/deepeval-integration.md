# Design: DeepEval Integration

> `civitas-contrib[deepeval]` — Bridging Civitas EvalLoop to DeepEval's metrics engine and test harness.

**Status:** Draft
**Package:** `civitas-contrib[deepeval]`
**Milestone:** M4
**Depends on:** `civitas` (EvalExporter, EvalEvent, EvalAgent), `deepeval` (external)
**Companion doc:** [Eval Framework](eval-framework.md)

---

## Problem Statement

Civitas defines the evaluation runtime (`EvalAgent`, `EvalExporter`, `CorrectionSignal`) but ships no metric implementations. Teams building agents need to evaluate task completion, tool correctness, and faithfulness — but implementing these metrics from scratch is expensive and error-prone.

DeepEval is an open-source LLM evaluation framework with 50+ built-in metrics, custom metric extensibility, and native pytest integration. It provides both the metrics engine and the offline test harness that Civitas lacks.

The integration must bridge these two systems without coupling either side. Civitas core must never import `deepeval`. DeepEval must not need to know about Civitas internals.

---

## Goals

1. Implement `EvalExporter` that runs DeepEval metrics on every `EvalEvent`
2. Map `EvalEvent` payloads to DeepEval's `LLMTestCase` cleanly
3. Map DeepEval metric scores to Civitas `CorrectionSignal` severities
4. Provide custom `BaseMetric` subclasses for governance-specific evaluation
5. Enable `deepeval test run` as an alternative to `pytest` for the offline harness

## Non-Goals

- Require DeepEval for Civitas eval to work (it's optional, via `EvalExporter` protocol)
- Integrate DeepEval's Confident AI cloud component by default (support, don't require)
- Replace Presidium's `GovernanceExporter` (different protocol, different purpose)

---

## Architecture

![DeepEval Integration — Data Flow](../assets/deepeval-integration.svg)

### Package Boundaries

| Component | Package | Rationale |
|---|---|---|
| `EvalEvent`, `EvalAgent`, `EvalExporter`, `CorrectionSignal` | `civitas` core | Runtime primitives — no external dependencies |
| `DeepEvalExporter`, custom metrics | `civitas-contrib[deepeval]` | Eval backend — same pattern as Arize/Fiddler exporters |
| `GovernanceEvalAgent`, `GovernanceMetrics` | `presidium-eval` | Governance-specific — depends on registry + policy |

Civitas core defines the protocol. `civitas-contrib[deepeval]` implements it. Presidium extends it with governance context.

---

## Design

### DeepEvalExporter

The central integration class. Implements Civitas's `EvalExporter` protocol and bridges to DeepEval's metric evaluation:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from civitas.evalloop import EvalEvent, EvalExporter
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase, ToolCall


@dataclass
class MetricResult:
    """Score and metadata from a single metric evaluation."""
    name: str
    score: float
    reason: str
    passed: bool


class DeepEvalExporter(EvalExporter):
    """Bridges Civitas EvalEvent to DeepEval metrics.

    Runs configured DeepEval metrics against each eval event and stores
    results for consumption by the EvalAgent's on_eval_event() hook.

    Usage:
        from deepeval.metrics import TaskCompletionMetric, ToolCorrectnessMetric

        exporter = DeepEvalExporter(
            metrics=[
                TaskCompletionMetric(threshold=0.7),
                ToolCorrectnessMetric(threshold=0.8),
            ]
        )
        eval_agent = EvalAgent("evaluator", exporters=[exporter])
    """

    def __init__(self, metrics: list[BaseMetric]) -> None:
        self._metrics = metrics
        self._last_results: dict[str, MetricResult] = {}

    @property
    def last_results(self) -> dict[str, MetricResult]:
        """Most recent metric results, keyed by metric name."""
        return self._last_results

    async def export(self, event: EvalEvent) -> None:
        """Run all configured metrics against the event."""
        test_case = self._event_to_test_case(event)
        if test_case is None:
            return

        self._last_results.clear()
        for metric in self._metrics:
            await metric.a_measure(test_case)
            self._last_results[metric.__name__] = MetricResult(
                name=metric.__name__,
                score=metric.score,
                reason=metric.reason or "",
                passed=metric.is_successful(),
            )

    def _event_to_test_case(self, event: EvalEvent) -> LLMTestCase | None:
        """Map EvalEvent payload to DeepEval LLMTestCase.

        Expected payload fields (all optional — metrics that require
        missing fields will score 0.0):

            task_description: str     → LLMTestCase.input
            output: str               → LLMTestCase.actual_output
            expected_output: str      → LLMTestCase.expected_output
            tools_called: list[dict]  → LLMTestCase.tools_called
            expected_tools: list[dict]→ LLMTestCase.expected_tools
            context: list[str]        → LLMTestCase.context
        """
        payload = event.payload
        task = payload.get("task_description", "")
        output = payload.get("output", "")

        if not task and not output:
            return None

        # Map tool dicts to DeepEval ToolCall objects
        tools_called = None
        if "tools_called" in payload:
            tools_called = [
                ToolCall(
                    name=tc.get("name", ""),
                    input=tc.get("input", {}),
                )
                for tc in payload["tools_called"]
            ]

        expected_tools = None
        if "expected_tools" in payload:
            expected_tools = [
                ToolCall(
                    name=tc.get("name", ""),
                    input=tc.get("input", {}),
                )
                for tc in payload["expected_tools"]
            ]

        return LLMTestCase(
            input=task,
            actual_output=output,
            expected_output=payload.get("expected_output"),
            tools_called=tools_called,
            expected_tools=expected_tools,
            context=payload.get("context"),
            additional_metadata=payload.get("metadata"),
        )
```

### EvalEvent Payload Contract

For the `DeepEvalExporter` to work, agents must emit `EvalEvent` with a payload that follows this contract:

```python
# Emitting an eval event from an agent
await self.emit_eval(
    event_type="task_complete",
    payload={
        "task_description": "Fix the type error in auth.ts",
        "output": "Modified auth.ts: changed line 42 from...",
        "expected_output": None,  # optional
        "tools_called": [
            {"name": "file_write", "input": {"path": "src/auth.ts"}},
            {"name": "shell_execute", "input": {"command": "pytest"}},
        ],
        "expected_tools": [
            {"name": "file_write", "input": {"path": "src/auth.ts"}},
        ],
        "context": ["Error: Type 'string' is not assignable to type 'number'"],
        "metadata": {
            "tests_passed": 42,
            "tests_total": 42,
            "coverage_delta": -0.02,
        },
    },
)
```

Fields are optional. Metrics that require a missing field will return a score of 0.0 — this is DeepEval's default behavior, not a Civitas decision.

### Score-to-CorrectionSignal Mapping

The `DeepEvalExporter` stores scores but does not emit `CorrectionSignal` — that's the `EvalAgent`'s responsibility. A utility function bridges the two:

```python
def scores_to_signal(
    results: dict[str, MetricResult],
    halt_threshold: float = 0.4,
    redirect_threshold: float = 0.7,
) -> CorrectionSignal | None:
    """Convert DeepEval metric results to a CorrectionSignal.

    Args:
        results: Metric results from DeepEvalExporter.last_results
        halt_threshold: Score below this triggers halt
        redirect_threshold: Score below this triggers redirect

    Returns:
        CorrectionSignal or None if all metrics pass
    """
    if not results:
        return None

    worst_score = min(r.score for r in results.values())
    failed = [r.name for r in results.values() if not r.passed]

    if not failed:
        return None

    if worst_score < halt_threshold:
        return CorrectionSignal(
            severity="halt",
            reason=f"Critical eval failure: {', '.join(failed)}",
            payload={"scores": {k: v.score for k, v in results.items()}},
        )

    if worst_score < redirect_threshold:
        return CorrectionSignal(
            severity="redirect",
            reason=f"Below threshold: {', '.join(failed)}",
            payload={"scores": {k: v.score for k, v in results.items()}},
        )

    return CorrectionSignal(
        severity="nudge",
        reason=f"Marginal scores: {', '.join(failed)}",
        payload={"scores": {k: v.score for k, v in results.items()}},
    )
```

### Built-in Metrics Used

DeepEval ships 50+ metrics. The following are recommended for agent evaluation out of the box:

| Metric | What it evaluates | Default threshold | Mode |
|---|---|---|---|
| `TaskCompletionMetric` | Did the agent accomplish the stated task? | 0.7 | LLM-as-Judge |
| `ToolCorrectnessMetric` | Did the agent select the right tools? | 0.8 | Hybrid (deterministic + LLM) |
| `ArgumentCorrectnessMetric` | Were tool arguments correct? | 0.7 | LLM-as-Judge |
| `PlanAdherenceMetric` | Did execution follow the declared plan? | 0.7 | LLM-as-Judge |
| `FaithfulnessMetric` | Is the output grounded in the context provided? | 0.6 | LLM-as-Judge |
| `HallucinationMetric` | Does the output contain fabricated information? | 0.5 | LLM-as-Judge |

All LLM-as-Judge metrics require a judge model. DeepEval supports configuring this globally:

```python
from deepeval import set_default_model
set_default_model("gpt-4o")  # or any model DeepEval supports
```

### Custom Metrics for Governance

Two custom `BaseMetric` subclasses ship with `civitas-contrib[deepeval]` for governance-specific evaluation. These use deterministic scoring (no LLM judge) for sub-millisecond in-flight performance:

```python
class ScopeDriftMetric(BaseMetric):
    """Evaluates whether agent actions stayed within the declared intent.

    Compares the set of tools/files actually used against the set declared
    in the intent declaration. Any undeclared action reduces the score.

    This is a deterministic metric — no LLM judge, sub-millisecond.
    """

    def __init__(self, threshold: float = 0.9) -> None:
        self.threshold = threshold

    async def a_measure(self, test_case: LLMTestCase) -> float:
        metadata = test_case.additional_metadata or {}
        declared = set(metadata.get("declared_actions", []))
        actual = set(metadata.get("actual_actions", []))

        if not actual:
            self.score = 1.0
        else:
            in_scope = actual & declared
            self.score = len(in_scope) / len(actual)

        out_of_scope = actual - declared
        self.reason = (
            f"{len(out_of_scope)} undeclared action(s): "
            f"{', '.join(sorted(out_of_scope)) or 'none'}"
        )
        self.success = self.score >= self.threshold
        return self.score

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self) -> str:
        return "Scope Drift"


class BudgetAdherenceMetric(BaseMetric):
    """Evaluates whether token/cost consumption is within budget.

    Deterministic — compares actual consumption against configured limits.
    """

    def __init__(self, threshold: float = 0.8) -> None:
        self.threshold = threshold

    async def a_measure(self, test_case: LLMTestCase) -> float:
        metadata = test_case.additional_metadata or {}
        tokens_used = metadata.get("tokens_used", 0)
        tokens_budget = metadata.get("tokens_budget", 1)
        cost_usd = metadata.get("cost_usd", 0.0)
        cost_budget_usd = metadata.get("cost_budget_usd", 1.0)

        token_ratio = min(1.0, tokens_used / max(tokens_budget, 1))
        cost_ratio = min(1.0, cost_usd / max(cost_budget_usd, 0.01))
        utilization = max(token_ratio, cost_ratio)

        # Score is inverse of utilization — 1.0 means no budget used
        self.score = max(0.0, 1.0 - utilization)
        self.reason = (
            f"Tokens: {tokens_used}/{tokens_budget} ({token_ratio:.0%}), "
            f"Cost: ${cost_usd:.2f}/${cost_budget_usd:.2f} ({cost_ratio:.0%})"
        )
        self.success = self.score >= self.threshold
        return self.score

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self) -> str:
        return "Budget Adherence"
```

### Offline Harness Integration

DeepEval provides `assert_test()` for pytest integration. The civitas test harness (`EvalTestRunner`) can delegate to it:

```python
# tests/evals/test_my_agent.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import TaskCompletionMetric, ToolCorrectnessMetric

from civitas.testing import EvalDataset

dataset = EvalDataset.from_json("datasets/my_agent_v1.json")


@pytest.mark.parametrize(
    "test_case",
    dataset.test_cases,
    ids=lambda tc: tc.metadata.get("id", "") if tc.metadata else "",
)
def test_agent_quality(test_case):
    # Run agent (or use recorded output)
    result = run_agent(test_case.input)

    assert_test(
        test_case=LLMTestCase(
            input=test_case.input.get("task_description", ""),
            actual_output=result.get("output", ""),
            expected_output=test_case.expected_output.get("output") if test_case.expected_output else None,
            tools_called=result.get("tools_called"),
            expected_tools=test_case.expected_tools,
        ),
        metrics=[
            TaskCompletionMetric(threshold=0.7),
            ToolCorrectnessMetric(threshold=0.8),
        ],
    )
```

Two runners, same metrics:

| Runner | Command | When | Metrics |
|---|---|---|---|
| `EvalTestRunner` | `uv run pytest tests/evals/` | CI, pre-merge | All metrics from Metric Registry |
| `deepeval test run` | `deepeval test run tests/evals/` | Dev, with dashboard | Same metrics + DeepEval's dashboard UI |

### In-Flight Latency Considerations

LLM-as-Judge metrics add latency and cost. For in-flight evaluation, the recommended pattern:

| Metric type | In-flight? | Latency | Cost |
|---|---|---|---|
| Deterministic (`ScopeDriftMetric`, `BudgetAdherenceMetric`) | Always | < 1ms | Zero |
| Hybrid (`ToolCorrectnessMetric`) | Configurable | ~100ms | Low |
| LLM-as-Judge (`TaskCompletionMetric`, `FaithfulnessMetric`) | Sampled or async | 1-5s | $0.01-0.05 per eval |

Recommendation: run deterministic metrics on every event. Run LLM-as-Judge metrics asynchronously (fire-and-forget to the exporter) or on a sampling basis (every Nth event). The Metric Registry's `in_flight: bool` flag controls this per metric.

---

## Module Layout

```
civitas-contrib/
  plugins/
    deepeval_exporter.py     # DeepEvalExporter (EvalExporter implementation)
    deepeval_metrics.py      # ScopeDriftMetric, BudgetAdherenceMetric
    deepeval_utils.py        # scores_to_signal(), payload mapping helpers
```

Install:

```bash
pip install civitas-contrib[deepeval]
```

This adds `deepeval` as an optional dependency. The exporter is discovered via Civitas's plugin loader when configured in topology YAML:

```yaml
plugins:
  exporters:
    - type: deepeval
      config:
        metrics:
          - TaskCompletionMetric:
              threshold: 0.7
          - ToolCorrectnessMetric:
              threshold: 0.8
          - ScopeDriftMetric:
              threshold: 0.9
        judge_model: gpt-4o
```

---

## Alternatives Considered

1. **Build metrics from scratch** — Expensive, error-prone, and misses DeepEval's ecosystem (50+ metrics, dataset management, regression tracking). Custom metrics are supported via `BaseMetric` — no need to reinvent the evaluation engine.

2. **Use DeepEval as the only eval path** — Creates a hard dependency. Teams using Arize or Langfuse for eval would be locked out. The `EvalExporter` protocol keeps the architecture open.

3. **Run DeepEval outside Civitas** — Loses the in-flight correction loop. The value proposition is that eval scores trigger `CorrectionSignal` in real time, not that they generate a dashboard after the fact.

4. **Put DeepEval integration in presidium-eval** — Wrong package boundary. DeepEval evaluates agent quality (general-purpose), not governance compliance (Presidium-specific). `civitas-contrib` is the right home — same as Anthropic/OpenAI provider implementations.

---

## Open Questions

- **Confident AI integration:** Should the exporter support DeepEval's optional cloud component for dataset management and dashboards? Proposal: support via config flag, off by default.
- **Judge model cost:** LLM-as-Judge metrics cost ~$0.01-0.05 per evaluation. At scale (1000 events/min), this is $600-3000/day. Should the integration expose a cost estimator? Should it enforce a per-window eval budget?
- **Metric versioning:** When a metric's scoring logic changes (DeepEval upgrade), historical scores become incomparable. Should the Metric Registry pin DeepEval versions per metric?
- **Multi-turn evaluation:** DeepEval supports `ConversationalTestCase` for multi-turn interactions. Should `EvalEvent` support a `conversation_id` to group events into multi-turn test cases?
