from __future__ import annotations

from datetime import UTC, datetime

import pytest

from presidium.model import TrustEvent, TrustTier
from presidium.scoring.config import WindowConfig
from presidium.scoring.events import EventContext
from presidium.scoring.spec import ScoringSpec
from presidium.trust import (
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
