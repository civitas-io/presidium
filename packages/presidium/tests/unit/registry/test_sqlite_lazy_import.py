"""Real regression test for a real, live packaging bug (2026-08-22).

`presidium/__init__.py` eagerly imports `SqliteRegistry`, and
`presidium.registry.sqlite` used to `import aiosqlite` unconditionally at
module level -- meaning a plain `pip install presidium` (no extras) could
not even `import presidium` at all. Confirmed live against the real
published v0.2.0 wheel in a fresh venv, not assumed. `aiosqlite` is only
genuinely needed at `SqliteRegistry._conn()` time now, imported lazily with
a helpful, real `pip install 'presidium[sqlite]'` error message.
"""

from __future__ import annotations

import builtins

import pytest

from presidium.errors import PresidiumError


def test_no_module_level_aiosqlite_import_in_source() -> None:
    """A cheap, precise, direct regression guard against reintroducing the
    exact real bug: presidium/registry/sqlite.py's own module-level source
    (outside any function/TYPE_CHECKING block) must never contain a bare
    `import aiosqlite` again -- that's exactly what broke `import presidium`
    for anyone without the `[sqlite]` extra, confirmed live against the
    real published v0.2.0 wheel in a fresh venv.
    """
    import inspect

    import presidium.registry.sqlite as sqlite_module

    source_lines = inspect.getsource(sqlite_module).splitlines()
    for line in source_lines:
        stripped = line.strip()
        if stripped == "import aiosqlite" and not line.startswith(("    ", "\t")):
            pytest.fail(
                "Found a module-level (unindented) 'import aiosqlite' -- this is exactly the "
                "bug that broke `import presidium` without the [sqlite] extra. It must stay "
                "inside TYPE_CHECKING or a lazy, function-local import."
            )


async def test_sqlite_registry_construction_does_not_require_aiosqlite() -> None:
    """Constructing a SqliteRegistry (not yet using it) must not touch
    aiosqlite at all -- only _conn() does, lazily, on first real use."""
    from presidium.registry.sqlite import SqliteRegistry

    registry = SqliteRegistry(":memory:")  # must not raise
    assert registry is not None


async def test_helpful_error_when_aiosqlite_genuinely_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real, user-facing error message when aiosqlite truly isn't
    installed and a real operation is attempted."""
    from presidium.registry.sqlite import SqliteRegistry

    real_import = builtins.__import__

    def _fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "aiosqlite":
            raise ImportError("simulated: aiosqlite is not installed")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    registry = SqliteRegistry(":memory:")
    with pytest.raises(PresidiumError, match="pip install 'presidium\\[sqlite\\]'"):
        await registry._conn()
