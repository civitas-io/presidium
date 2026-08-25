#!/usr/bin/env python3
"""Adversarial regex-backtracking (ReDoS) check for the MCP governance regex
patterns -- security-relevant, not just a performance number. Python's `re`
is a backtracking engine (not guaranteed-linear like RE2), and
PIIDetector's own `credit_card` pattern (`\\b(?:\\d[ -]*?){13,19}\\b`) has the
general shape (a bounded repetition wrapping a variable-length inner
quantifier) that's a real, known category of catastrophic-backtracking risk.

Run as a SEPARATE PROCESS with a hard wall-clock timeout per size (via
multiprocessing), so a genuinely catastrophic case can't hang this script
itself -- if a size times out, that IS the finding, not a bug in the harness.

Usage:
    uv run --package presidium-contrib python benchmarks/redos_check.py
"""

from __future__ import annotations

import multiprocessing
import time

from presidium_contrib.mcp_gateway.pii import _DEFAULT_PATTERNS  # noqa: PLC2701
from presidium_contrib.mcp_gateway.redaction import _CREDENTIAL_PATTERNS  # noqa: PLC2701

_TIMEOUT_SECONDS = 3.0


def _adversarial_credit_card_input(n_digits: int) -> str:
    """First attempt (kept for the record, see _v2 below for the real
    adversarial shape): single spaces between digits mean `\\b` is trivially
    satisfiable at nearly every digit/space boundary, so this input never
    forces genuine backtracking exploration -- not adversarial.
    """
    return ("1 " * n_digits) + "x"


def _adversarial_credit_card_input_v2(n_digits: int) -> str:
    """The real adversarial shape: digits separated by RUNS of 2+ separator
    characters (dashes), so `[ -]*?`'s own internal choice of "how many
    separators belong to this iteration vs. spill into the next" is
    genuinely ambiguous -- multiple ways to partition the same input across
    the outer {13,19} repetitions. Ends in a non-word, non-separator
    character so the only possible `\\b` is at the very end, forcing the
    engine to exhaust every partition before concluding failure -- the
    actual shape catastrophic-backtracking reports for this regex class
    describe, not the first (too-easy) attempt above.
    """
    return ("1--" * n_digits) + "!"


def _run_pattern(
    pattern_source: str, text: str, result_queue: multiprocessing.Queue[float]
) -> None:
    import re

    compiled = re.compile(pattern_source)
    t0 = time.perf_counter()
    compiled.search(text)
    result_queue.put(time.perf_counter() - t0)


def _timed_search(pattern_source: str, text: str) -> float | None:
    """Returns elapsed seconds, or None if it hit the hard timeout (the
    real, security-relevant finding)."""
    ctx = multiprocessing.get_context("spawn")
    q: multiprocessing.Queue[float] = ctx.Queue()
    p = ctx.Process(target=_run_pattern, args=(pattern_source, text, q))
    p.start()
    p.join(timeout=_TIMEOUT_SECONDS)
    if p.is_alive():
        p.terminate()
        p.join()
        return None
    return q.get() if not q.empty() else None


def main() -> None:
    print(
        f"Hard per-attempt timeout: {_TIMEOUT_SECONDS}s "
        "(a timeout IS the finding, not a harness bug)"
    )
    print()
    print("=== credit_card pattern -- adversarial input, increasing size ===")
    credit_card_pattern = _DEFAULT_PATTERNS["credit_card"].pattern
    for n in (10, 15, 20, 25, 30, 40, 50, 70, 100):
        text = _adversarial_credit_card_input(n)
        elapsed = _timed_search(credit_card_pattern, text)
        if elapsed is None:
            print(
                f"  n_digits={n:>4} (len={len(text):>5}): "
                f"TIMEOUT (>{_TIMEOUT_SECONDS}s) -- catastrophic"
            )
            print("  Stopping escalation -- confirmed catastrophic, no need to go further.")
            break
        print(f"  n_digits={n:>4} (len={len(text):>5}): {elapsed * 1000:>10.3f} ms")

    print()
    print("=== credit_card pattern -- v2 adversarial input (ambiguous separator runs) ===")
    for n in (10, 13, 15, 17, 19, 20, 22, 25, 28, 30):
        text = _adversarial_credit_card_input_v2(n)
        elapsed = _timed_search(credit_card_pattern, text)
        if elapsed is None:
            print(
                f"  n_digits={n:>4} (len={len(text):>5}): TIMEOUT (>{_TIMEOUT_SECONDS}s) "
                "-- catastrophic"
            )
            print("  Stopping escalation -- confirmed catastrophic, no need to go further.")
            break
        print(f"  n_digits={n:>4} (len={len(text):>5}): {elapsed * 1000:>10.3f} ms")

    print()
    print("=== other PII patterns -- same adversarial-shape smoke test ===")
    for name, pattern in _DEFAULT_PATTERNS.items():
        if name == "credit_card":
            continue
        text = ("a" * 200) + "@" + ("b" * 200) + "!"  # generic near-miss adversarial text
        elapsed = _timed_search(pattern.pattern, text)
        status = "TIMEOUT" if elapsed is None else f"{elapsed * 1000:.3f} ms"
        print(f"  {name:<14}: {status}")

    print()
    print("=== redaction.py credential patterns -- same smoke test ===")
    for pattern in _CREDENTIAL_PATTERNS:
        text = ("token=" + "a" * 500) + " " + ("bearer " + "b" * 500)
        elapsed = _timed_search(pattern.pattern, text)
        status = "TIMEOUT" if elapsed is None else f"{elapsed * 1000:.3f} ms"
        print(f"  {pattern.pattern[:40]!r:<44}: {status}")


if __name__ == "__main__":
    main()
