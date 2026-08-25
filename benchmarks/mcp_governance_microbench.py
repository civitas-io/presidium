#!/usr/bin/env python3
"""Isolated microbenchmark for the three, previously-unbenchmarked MCP
governance primitives (docs/vision/roadmap.md's M8 section named this a real,
separate follow-up: "CPU-bound string processing over potentially large tool
outputs, a second real GIL-bound cost center... not assumed fine by
proximity").

Benchmarks PIIDetector.scan_dict()/mask_dict() and redact_dict() at varying
payload sizes (they scale with tool-OUTPUT size, unlike CEL policy eval which
scales with rule COUNT) -- and PoisoningDetector.check(), which scales with
tool-metadata size instead (name/description/schema), to confirm it stays
cheap regardless of how large a tool's actual result is.

Usage:
    uv run --package presidium-contrib python benchmarks/mcp_governance_microbench.py
"""

from __future__ import annotations

import random
import statistics
import time

from presidium_contrib.mcp_gateway.pii import PIIDetector
from presidium_contrib.mcp_gateway.poisoning import PoisoningDetector
from presidium_contrib.mcp_gateway.redaction import redact_dict

_LOREM_WORDS = (
    "the quick brown fox jumps over the lazy dog while agents orchestrate "
    "governed tool calls across a distributed civitas runtime with real "
    "policy enforcement and structured audit logging enabled by default"
).split()


def _make_payload(
    size_bytes: int, *, pii_density: float = 0.02, seed: int = 42
) -> dict[str, object]:
    """A realistic-shaped tool result: prose text with occasional real PII
    substrings sprinkled in (not all-matching, not all-clean -- a real scan
    has to walk the whole string either way, but sprinkled matches exercise
    the match-collection path too, not just early-continue on no-match).
    """
    rng = random.Random(seed)
    pii_samples = [
        "john.doe@example.com",
        "555-867-5309",
        "192.168.1.42",
        "123-45-6789",
    ]
    words: list[str] = []
    current_len = 0
    while current_len < size_bytes:
        if rng.random() < pii_density:
            word = rng.choice(pii_samples)
        else:
            word = rng.choice(_LOREM_WORDS)
        words.append(word)
        current_len += len(word) + 1
    text = " ".join(words)
    return {"output": text, "metadata": {"source": "bench", "nested": {"detail": text[:200]}}}


def _time_calls(fn: object, iterations: int) -> dict[str, float]:
    samples_us: list[float] = []
    start = time.perf_counter()
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()  # type: ignore[operator]
        samples_us.append((time.perf_counter() - t0) * 1_000_000)
    wall = time.perf_counter() - start
    samples_us.sort()

    def pct(p: float) -> float:
        idx = min(int(len(samples_us) * p), len(samples_us) - 1)
        return samples_us[idx]

    return {
        "mean_us": statistics.mean(samples_us),
        "p50_us": pct(0.50),
        "p95_us": pct(0.95),
        "p99_us": pct(0.99),
        "calls_per_sec": iterations / wall,
    }


def _print_row(label: str, size_bytes: int, r: dict[str, float]) -> None:
    print(
        f"{label:<16} {size_bytes:>10} {r['mean_us']:>12.1f} {r['p50_us']:>12.1f} "
        f"{r['p95_us']:>12.1f} {r['p99_us']:>12.1f} {r['calls_per_sec']:>12.1f}"
    )


def main() -> None:
    sizes = [1_000, 10_000, 100_000, 1_000_000]
    header = (
        f"{'op':<16} {'size_bytes':>10} {'mean_us':>12} {'p50_us':>12} "
        f"{'p95_us':>12} {'p99_us':>12} {'calls/sec':>12}"
    )
    print(header)

    detector = PIIDetector()
    for size in sizes:
        payload = _make_payload(size)
        iterations = max(5, min(200, 2_000_000 // size))

        _print_row(
            "pii.scan_dict",
            size,
            _time_calls(lambda p=payload: detector.scan_dict(p), iterations),
        )
        _print_row(
            "pii.mask_dict",
            size,
            _time_calls(lambda p=payload: detector.mask_dict(p), iterations),
        )
        _print_row(
            "redact.redact_dict",
            size,
            _time_calls(lambda p=payload: redact_dict(p), iterations),
        )

    print()
    print("poisoning.check() -- scales with tool metadata size, NOT result size:")
    poisoning = PoisoningDetector()
    description = "A real tool description of realistic length for a typical MCP tool definition."
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
    }
    poisoning.approve_tool("bench_tool", description, schema, approved_by="bench")
    r = _time_calls(lambda: poisoning.check("bench_tool", description, schema), 5000)
    _print_row("poisoning.check", len(description) + len(str(schema)), r)


if __name__ == "__main__":
    main()
