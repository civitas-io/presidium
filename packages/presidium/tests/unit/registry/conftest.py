from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from presidium.registry.memory import InMemoryRegistry
from presidium.registry.sqlite import SqliteRegistry


@pytest.fixture(params=["memory", "sqlite"])
async def registry(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[InMemoryRegistry | SqliteRegistry, None]:
    if request.param == "memory":
        yield InMemoryRegistry()
    else:
        reg = SqliteRegistry(":memory:")
        yield reg
        await reg.close()
