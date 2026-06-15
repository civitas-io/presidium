from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from presidium.errors import MissingAttributionError, SpecMismatchError
from presidium.model import TrustEvent, TrustTier
from presidium.scoring.config import WindowConfig
from presidium.scoring.events import EventContext
from presidium.scoring.spec import ScoringSpec
from presidium.trust import (
    LinearTrustScore,
    WindowedTrustScorer,
)
from presidium.trust.cold_start import (
    ColdStartStrategy,
    NeutralStart,
    OptimisticStart,
    PessimisticStart,
)
from presidium.trust.core import TrustScorer
from presidium.trust.protocols import (
    ContextualTrustScorer,
    IntrospectableScorer,
    QueryableScorer,
)


class TestColdStartProtocol:
    def test_optimistic_satisfies_protocol(self) -> None:
        assert isinstance(OptimisticStart(), ColdStartStrategy)

    def test_neutral_satisfies_protocol(self) -> None:
        assert isinstance(NeutralStart(), ColdStartStrategy)

    def test_pessimistic_satisfies_protocol(self) -> None:
        assert isinstance(PessimisticStart(), ColdStartStrategy)


class TestColdStartValues:
    def test_optimistic(self) -> None:
        s = OptimisticStart()
        assert s.initial_value() == 0.7
        assert s.min_events_for_normal == 0

    def test_neutral(self) -> None:
        s = NeutralStart()
        assert s.initial_value() == 0.5
        assert s.min_events_for_normal == 0

    def test_pessimistic(self) -> None:
        s = PessimisticStart(min_events=10)
        assert s.initial_value() == 0.2
        assert s.min_events_for_normal == 10

    def test_pessimistic_default_min(self) -> None:
        s = PessimisticStart()
        assert s.min_events_for_normal == 5


class TestWindowedTrustScorerProtocol:
    def test_satisfies_trust_scorer(self) -> None:
        scorer = WindowedTrustScorer()
        assert isinstance(scorer, TrustScorer)

    def test_satisfies_contextual(self) -> None:
        scorer = WindowedTrustScorer()
        assert isinstance(scorer, ContextualTrustScorer)

    def test_satisfies_introspectable(self) -> None:
        scorer = WindowedTrustScorer()
        assert isinstance(scorer, IntrospectableScorer)

    def test_satisfies_queryable(self) -> None:
        scorer = WindowedTrustScorer()
        assert isinstance(scorer, QueryableScorer)


class TestWindowedTrustScorerBasic:
    def test_default_value(self) -> None:
        scorer = WindowedTrustScorer()
        assert scorer.value == pytest.approx(0.5, abs=0.001)
        assert scorer.tier == TrustTier.STANDARD

    def test_success_increments(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value == pytest.approx(0.52, abs=0.01)

    def test_failure_decrements(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        assert scorer.value == pytest.approx(0.45, abs=0.01)

    def test_policy_violation(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.POLICY_VIOLATION)
        assert scorer.value == pytest.approx(0.40, abs=0.01)

    def test_tier_transition(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(initial_value=0.69, clock=lambda: now)
        assert scorer.tier == TrustTier.STANDARD
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.tier == TrustTier.TRUSTED

    def test_last_updated(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.last_updated == now


class TestWindowedTrustScorerWindowing:
    def test_old_events_excluded(self) -> None:
        now = datetime(2026, 6, 15, tzinfo=UTC)
        scorer = WindowedTrustScorer(
            window=WindowConfig(max_age_hours=168.0),
            clock=lambda: now,
        )
        # Manually inject an old event that should be excluded by window
        old = datetime(2026, 1, 1, tzinfo=UTC)
        from presidium.scoring.events import Event

        scorer._events.append(
            Event(id="old", timestamp=old, tags={"type": "failure"}, values={"delta": -0.05})
        )
        scorer.record_event(TrustEvent.SUCCESS)
        # Old failure aged out, only success in window
        assert scorer.value == pytest.approx(0.52, abs=0.02)

    def test_max_events_window(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(
            window=WindowConfig(max_events=2, max_age_hours=None),
            clock=lambda: now,
        )
        for _ in range(5):
            scorer.record_event(TrustEvent.FAILURE)
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.SUCCESS)
        # Only last 2 events (both success) in window
        assert scorer.value > 0.5


class TestWindowedTrustScorerColdStart:
    def test_optimistic_cold_start(self) -> None:
        scorer = WindowedTrustScorer(cold_start=OptimisticStart())
        assert scorer.value == pytest.approx(0.7, abs=0.001)

    def test_pessimistic_cold_start(self) -> None:
        scorer = WindowedTrustScorer(cold_start=PessimisticStart(min_events=5))
        assert scorer.value == pytest.approx(0.2, abs=0.001)

    def test_pessimistic_warmup_blend(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(
            cold_start=PessimisticStart(min_events=10),
            clock=lambda: now,
        )
        # After 5 events, should blend between cold-start (0.2) and computed
        for _ in range(5):
            scorer.record_event(TrustEvent.SUCCESS)
        val = scorer.value
        assert 0.2 < val < 0.6  # blended, not pure cold-start or pure computed


class TestWindowedTrustScorerControllability:
    def test_uncontrollable_events_filtered(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(
            controllability_filter=True,
            clock=lambda: now,
        )
        scorer.record_event(
            TrustEvent.FAILURE,
            context=EventContext(controllable=False, reason="network timeout"),
        )
        # Uncontrollable failure should not affect score
        assert scorer.value == pytest.approx(0.5, abs=0.01)

    def test_controllable_events_counted(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(
            controllability_filter=True,
            clock=lambda: now,
        )
        scorer.record_event(
            TrustEvent.FAILURE,
            context=EventContext(controllable=True),
        )
        assert scorer.value == pytest.approx(0.45, abs=0.01)


class TestWindowedTrustScorerSpec:
    def test_spec_returns_scoring_spec(self) -> None:
        scorer = WindowedTrustScorer()
        spec = scorer.spec
        assert isinstance(spec, ScoringSpec)
        assert spec.scorer_type == "presidium.trust.windowed.WindowedTrustScorer"
        assert spec.initial_value == 0.5

    def test_spec_hash_deterministic(self) -> None:
        s1 = WindowedTrustScorer()
        s2 = WindowedTrustScorer()
        assert s1.spec.spec_hash == s2.spec.spec_hash

    def test_spec_hash_changes_with_config(self) -> None:
        s1 = WindowedTrustScorer(initial_value=0.5)
        s2 = WindowedTrustScorer(initial_value=0.7)
        assert s1.spec.spec_hash != s2.spec.spec_hash


class TestWindowedTrustScorerQuery:
    def test_recent_events(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.FAILURE)
        recent = scorer.recent_events(limit=5)
        assert len(recent) == 2
        assert recent[0]["type"] == "failure"  # most recent first
        assert recent[1]["type"] == "success"

    def test_recent_events_limited(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        for _ in range(20):
            scorer.record_event(TrustEvent.SUCCESS)
        recent = scorer.recent_events(limit=5)
        assert len(recent) == 5


class TestWindowedTrustScorerSetValue:
    def test_set_value_resets(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.9)
        assert scorer.value == pytest.approx(0.9, abs=0.001)
        assert scorer.tier == TrustTier.TRUSTED


# ---------------------------------------------------------------------------
# FR-E.1: Spec Pinning
# ---------------------------------------------------------------------------


class TestSpecPinning:
    def test_pinned_hash_matches(self) -> None:
        scorer = WindowedTrustScorer()
        pinned = scorer.spec.spec_hash
        scorer2 = WindowedTrustScorer(pinned_spec_hash=pinned)
        assert scorer2.spec.spec_hash == pinned

    def test_pinned_hash_mismatch_raises(self) -> None:
        with pytest.raises(SpecMismatchError) as exc_info:
            WindowedTrustScorer(pinned_spec_hash="wrong_hash_value")
        assert exc_info.value.expected == "wrong_hash_value"

    def test_no_pin_allows_any_config(self) -> None:
        scorer = WindowedTrustScorer(initial_value=0.9)
        assert scorer.value == pytest.approx(0.9, abs=0.01)


# ---------------------------------------------------------------------------
# FR-E.2: Override Attribution
# ---------------------------------------------------------------------------


class TestOverrideAttribution:
    def test_human_override_without_context_raises(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        with pytest.raises(MissingAttributionError):
            scorer.record_event(TrustEvent.HUMAN_OVERRIDE)

    def test_human_override_without_actor_id_raises(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        with pytest.raises(MissingAttributionError):
            scorer.record_event(
                TrustEvent.HUMAN_OVERRIDE,
                context=EventContext(actor_id=None),
            )

    def test_human_override_with_actor_id_accepted(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(
            TrustEvent.HUMAN_OVERRIDE,
            context=EventContext(actor_id="admin@example.com"),
        )
        recent = scorer.recent_events(limit=1)
        assert len(recent) == 1

    def test_non_override_events_dont_require_attribution(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.record_event(TrustEvent.POLICY_VIOLATION)
        assert len(scorer.recent_events(limit=10)) == 3


# ---------------------------------------------------------------------------
# FR-E.3: Performance Budget
# ---------------------------------------------------------------------------


class TestPerformanceBudget:
    def test_value_read_under_1ms_100_events(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        for _ in range(100):
            scorer.record_event(TrustEvent.SUCCESS)

        times = []
        for _ in range(100):
            start = time.perf_counter_ns()
            _ = scorer.value
            elapsed_ns = time.perf_counter_ns() - start
            times.append(elapsed_ns)

        times.sort()
        p99_ns = times[98]
        assert p99_ns < 1_000_000, f"p99 read latency {p99_ns/1000:.0f}μs exceeds 1ms"

    def test_tier_read_under_1ms_100_events(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        for _ in range(100):
            scorer.record_event(TrustEvent.SUCCESS)

        times = []
        for _ in range(100):
            start = time.perf_counter_ns()
            _ = scorer.tier
            elapsed_ns = time.perf_counter_ns() - start
            times.append(elapsed_ns)

        times.sort()
        p99_ns = times[98]
        assert p99_ns < 1_000_000, f"p99 tier latency {p99_ns/1000:.0f}μs exceeds 1ms"


# ---------------------------------------------------------------------------
# FR-E.4: Zero-Downtime Migration (M2 events readable by M3 scorers)
# ---------------------------------------------------------------------------


class TestZeroDowntimeMigration:
    def test_m2_trust_events_work_in_m3_scorer(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now)
        for event in TrustEvent:
            if event == TrustEvent.HUMAN_OVERRIDE:
                scorer.record_event(
                    event, context=EventContext(actor_id="migration@system")
                )
            else:
                scorer.record_event(event)
        assert 0.0 <= scorer.value <= 1.0

    def test_m2_linear_and_m3_windowed_accept_same_events(self) -> None:
        linear = LinearTrustScore(initial_value=0.5)
        now = datetime.now(UTC)
        windowed = WindowedTrustScorer(clock=lambda: now)

        linear.record_event(TrustEvent.SUCCESS)
        windowed.record_event(TrustEvent.SUCCESS)
        linear.record_event(TrustEvent.FAILURE)
        windowed.record_event(TrustEvent.FAILURE)

        assert 0.0 <= linear.value <= 1.0
        assert 0.0 <= windowed.value <= 1.0


# ---------------------------------------------------------------------------
# FR-E.5: Determinism Contract
# ---------------------------------------------------------------------------


class TestDeterminismContract:
    def test_linear_is_deterministic(self) -> None:
        assert LinearTrustScore.deterministic is True

    def test_windowed_is_deterministic(self) -> None:
        assert WindowedTrustScorer.deterministic is True

    def test_determinism_as_instance_attribute(self) -> None:
        scorer = WindowedTrustScorer()
        assert scorer.deterministic is True


# ---------------------------------------------------------------------------
# FR-E.6: OpenTelemetry (no-op when not installed)
# ---------------------------------------------------------------------------


class TestTelemetryNoOp:
    def test_record_event_works_without_otel(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now, agent_id="test-agent")
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value == pytest.approx(0.52, abs=0.01)

    def test_value_read_works_without_otel(self) -> None:
        now = datetime.now(UTC)
        scorer = WindowedTrustScorer(clock=lambda: now, agent_id="test-agent")
        assert scorer.value == pytest.approx(0.5, abs=0.001)
