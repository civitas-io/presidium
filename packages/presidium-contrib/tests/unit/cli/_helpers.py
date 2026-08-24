"""Shared CLI test helpers.

Real, necessary fix, not theoretical: a real CI run (Python 3.12, a narrower default terminal
width than this local dev machine) failed on `test_registry_list_nonexistent_db_exits_zero_
with_a_warning` -- Rich's own Table/text wrapping split "does-not-exist.db" itself across a
line break (`does-not-exist.d\nb`) because the CI runner's longer absolute tmp path pushed the
wrap point into the middle of the filename. `civitas.cli`'s own test suite already documents
"never assert on Rich-rendered text substrings" as a real, hard-won lesson (rendering width is
environment-dependent) -- this file's own `unwrapped()` is the concrete fix that lets tests
still assert on real content (agent names, error messages, computed values) without being
fragile to exactly where Rich happens to wrap a line on any given terminal width.
"""

from __future__ import annotations


def unwrapped(output: str) -> str:
    """Strip Rich's own line-wrap newlines so a substring assertion can't fail purely because
    the terminal happened to be narrow enough to split the text being checked for.
    """
    return output.replace("\n", "")
