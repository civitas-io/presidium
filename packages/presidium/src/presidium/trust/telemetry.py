"""Optional OpenTelemetry instrumentation for trust operations (FR-E.6).

Uses a no-op tracer when opentelemetry-api is not installed, so callers
never need to guard imports.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator


_SCOPE_NAME = "presidium.trust"

_ATTR_AGENT_ID = "trust.agent_id"
_ATTR_EVENT_TYPE = "trust.event_type"
_ATTR_VALUE = "trust.value"
_ATTR_TIER = "trust.tier"
_ATTR_SPEC_HASH = "trust.spec_hash"


class _SpanLike(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...  # noqa: ANN401


class _NoOpSpan:
    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ANN401
        pass


_tracer: Any = None


def _get_tracer() -> Any:  # noqa: ANN401
    global _tracer  # noqa: PLW0603
    if _tracer is not None:
        return _tracer
    try:
        from opentelemetry import trace

        _tracer = trace.get_tracer(_SCOPE_NAME)
    except ImportError:
        _tracer = None
    return _tracer


@contextmanager
def trust_span(
    operation: str,
    *,
    agent_id: str | None = None,
) -> Iterator[_SpanLike]:
    tracer = _get_tracer()
    if tracer is None:
        yield _NoOpSpan()
        return

    with tracer.start_as_current_span(f"trust.{operation}") as span:
        if agent_id is not None:
            span.set_attribute(_ATTR_AGENT_ID, agent_id)
        yield span


def set_trust_attributes(
    span: _SpanLike,
    *,
    event_type: str | None = None,
    value: float | None = None,
    tier: str | None = None,
    spec_hash: str | None = None,
) -> None:
    if event_type is not None:
        span.set_attribute(_ATTR_EVENT_TYPE, event_type)
    if value is not None:
        span.set_attribute(_ATTR_VALUE, value)
    if tier is not None:
        span.set_attribute(_ATTR_TIER, tier)
    if spec_hash is not None:
        span.set_attribute(_ATTR_SPEC_HASH, spec_hash)
