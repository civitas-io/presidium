#!/usr/bin/env python3
"""Generates a Rego policy equivalent to rule_gen.py's synthetic rule set --
N-1 distractor rules that never match the benchmark request, plus one
terminal allow -- so OPA and Presidium are benchmarked against the exact same
logical workload shape (same match count, same distractor-scan cost),
matching the council's own "one real, fair, same-conditions comparison"
recommendation in docs/design/performance-research.md.

Usage:
    python benchmarks/gen_opa_policy.py --rules 20 > benchmarks/opa_policy/bench.rego
"""

from __future__ import annotations

import argparse


def generate(count: int) -> str:
    lines = [
        "package bench",
        "",
        "import rego.v1",
        "",
        "default allow := false",
        "",
    ]
    for i in range(count - 1):
        lines.append(f"# distractor {i} -- never matches the benchmark request")
        lines.append(f'deny_reason_{i} if input.resource == "tool:never-matches-{i}"')
        lines.append("")
    lines.append("allow if {")
    lines.append('    input.resource == "tool:benchmark-target"')
    for i in range(count - 1):
        lines.append(f"    not deny_reason_{i}")
    lines.append("}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=int, required=True)
    args = parser.parse_args()
    print(generate(args.rules))
