from __future__ import annotations

from datetime import UTC, datetime

import pytest

from presidium.errors import MissingAttributionError
from presidium.model import TrustEvent, TrustTier
from presidium.scoring.events import EventContext
from presidium.scoring.spec import ScoringSpec
from presidium.trust import TrustScorer
from presidium.trust.protocols import IntrospectableScorer, QueryableScorer
from presidium_contrib.trust.scorer import LearningTrustScorer


class TestProtocol:
    def test_satisfies_trust_scorer(self) -> None:
        scorer = LearningTrustScorer()
        assert isinstance(scorer, TrustScorer)

    def test_satisfies_introspectable(self) -> None:
        scorer = LearningTrustScorer()
        assert isinstance(scorer, IntrospectableScorer)

    def test_satisfies_queryable(self) -> None:
        scorer = LearningTrustScorer()
        assert isinstance(scorer, QueryableScorer)

    def test_deterministic_is_false(self) -> None:
        scorer = LearningTrustScorer()
        assert scorer.deterministic is False


class TestBasicScoring:
    def test_default_value(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        assert scorer.value == pytest.approx(0.5, abs=0.001)
        assert scorer.tier == TrustTier.STANDARD

    def test_success_increments(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value == pytest.approx(0.52, abs=0.01)

    def test_failure_decrements(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        assert scorer.value == pytest.approx(0.45, abs=0.01)

    def test_policy_violation_decrements_more(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.POLICY_VIOLATION)
        assert scorer.value == pytest.approx(0.40, abs=0.01)

    def test_clamped_at_bounds(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(initial_value=0.99, clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value <= 1.0

        scorer2 = LearningTrustScorer(initial_value=0.02, clock=lambda: now)
        scorer2.record_event(TrustEvent.POLICY_VIOLATION)
        assert scorer2.value >= 0.0


class TestCustomWeights:
    def test_custom_weights_applied(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(
            weights={TrustEvent.SUCCESS: 0.10, TrustEvent.FAILURE: -0.20},
            clock=lambda: now,
        )
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value == pytest.approx(0.60, abs=0.01)

    def test_adjust_weights(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.adjust_weights({TrustEvent.FAILURE: -0.01})
        scorer.record_event(TrustEvent.FAILURE)
        assert scorer.value == pytest.approx(0.49, abs=0.01)

    def test_weights_property_returns_copy(self) -> None:
        scorer = LearningTrustScorer()
        w = scorer.weights
        w[TrustEvent.SUCCESS] = 999.0
        assert scorer.weights[TrustEvent.SUCCESS] == pytest.approx(0.02)


class TestJournal:
    def test_events_recorded_in_journal(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.FAILURE)
        assert len(scorer.journal) == 2
        assert scorer.journal[0].event == TrustEvent.SUCCESS
        assert scorer.journal[1].event == TrustEvent.FAILURE

    def test_journal_captures_before_after(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        entry = scorer.journal[0]
        assert entry.value_before == pytest.approx(0.5, abs=0.01)
        assert entry.value_after == pytest.approx(0.45, abs=0.01)
        assert entry.tier_before == TrustTier.STANDARD
        assert entry.tier_after == TrustTier.STANDARD

    def test_set_value_recorded_as_human_override(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.set_value(0.9)
        assert len(scorer.journal) == 1
        assert scorer.journal[0].event == TrustEvent.HUMAN_OVERRIDE
        assert scorer.journal[0].context == {"set_value": 0.9}

    def test_context_dict_passed_through(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS, context={"tool": "web_search"})
        assert scorer.journal[0].context == {"tool": "web_search"}

    def test_journal_returns_copy(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        j = scorer.journal
        j.clear()
        assert len(scorer.journal) == 1


class TestLearning:
    def test_learns_from_override_after_harsh_penalty(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)

        old_failure_weight = scorer.weights[TrustEvent.FAILURE]
        scorer.learn_from_history(learning_rate=0.5)
        new_failure_weight = scorer.weights[TrustEvent.FAILURE]

        assert new_failure_weight > old_failure_weight

    def test_learns_from_override_after_generous_reward(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.set_value(0.45)

        old_success_weight = scorer.weights[TrustEvent.SUCCESS]
        scorer.learn_from_history(learning_rate=0.5)
        new_success_weight = scorer.weights[TrustEvent.SUCCESS]

        assert new_success_weight < old_success_weight

    def test_no_learning_without_overrides(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.FAILURE)
        old_weights = scorer.weights
        scorer.learn_from_history()
        assert scorer.weights == old_weights

    def test_returns_updated_weights(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        result = scorer.learn_from_history()
        assert TrustEvent.FAILURE in result

    def test_skips_consecutive_overrides(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.set_value(0.3)
        scorer.set_value(0.6)
        old_weights = scorer.weights
        scorer.learn_from_history()
        assert scorer.weights == old_weights

    def test_multiple_overrides_average(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.48)

        scorer.learn_from_history(learning_rate=1.0)
        assert scorer.weights[TrustEvent.FAILURE] > -0.05

    def test_bounded_weight_delta(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(max_weight_delta=0.01, clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.90)
        before = scorer.weights[TrustEvent.FAILURE]
        scorer.learn_from_history(learning_rate=10.0)
        after = scorer.weights[TrustEvent.FAILURE]
        assert abs(after - before) <= 0.01 + 1e-9

    def test_learning_audit_recorded(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        scorer.learn_from_history()
        assert len(scorer.learning_audits) == 1
        audit = scorer.learning_audits[0]
        assert audit.events_considered == 1
        assert audit.rationale == "human_override_feedback"


class TestOverrideAttribution:
    def test_human_override_requires_actor_id_with_event_context(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        with pytest.raises(MissingAttributionError):
            scorer.record_event(
                TrustEvent.HUMAN_OVERRIDE,
                context=EventContext(actor_id=None),
            )

    def test_human_override_requires_context(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        with pytest.raises(MissingAttributionError):
            scorer.record_event(TrustEvent.HUMAN_OVERRIDE)

    def test_human_override_accepted_with_actor_id(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(
            TrustEvent.HUMAN_OVERRIDE,
            context=EventContext(actor_id="admin@example.com"),
        )
        assert len(scorer.journal) == 1

    def test_human_override_dict_context_not_sufficient(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        with pytest.raises(MissingAttributionError):
            scorer.record_event(
                TrustEvent.HUMAN_OVERRIDE,
                context={"actor_id": "admin@example.com"},
            )


class TestSpec:
    def test_returns_scoring_spec(self) -> None:
        scorer = LearningTrustScorer()
        spec = scorer.spec
        assert isinstance(spec, ScoringSpec)
        assert spec.scorer_type == "presidium_contrib.trust.scorer.LearningTrustScorer"

    def test_spec_hash_deterministic(self) -> None:
        s1 = LearningTrustScorer()
        s2 = LearningTrustScorer()
        assert s1.spec.spec_hash == s2.spec.spec_hash


class TestRecentEvents:
    def test_recent_events(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.FAILURE)
        recent = scorer.recent_events(limit=5)
        assert len(recent) == 2
        assert recent[0]["type"] == "failure"
        assert recent[1]["type"] == "success"

    def test_recent_events_limited(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(clock=lambda: now)
        for _ in range(20):
            scorer.record_event(TrustEvent.SUCCESS)
        recent = scorer.recent_events(limit=5)
        assert len(recent) == 5


class TestLearnCooldown:
    def test_cooldown_blocks_rapid_learning(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(learn_cooldown_hours=24.0, clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)

        before = scorer.weights[TrustEvent.FAILURE]
        scorer.learn_from_history(learning_rate=0.5)
        after_first = scorer.weights[TrustEvent.FAILURE]
        assert after_first != before

        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        scorer.learn_from_history(learning_rate=0.5)
        after_second = scorer.weights[TrustEvent.FAILURE]
        assert after_second == after_first

    def test_cooldown_none_allows_unlimited(self) -> None:
        now = datetime.now(UTC)
        scorer = LearningTrustScorer(learn_cooldown_hours=None, clock=lambda: now)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        scorer.learn_from_history(learning_rate=0.5)
        first = scorer.weights[TrustEvent.FAILURE]

        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        scorer.learn_from_history(learning_rate=0.5)
        second = scorer.weights[TrustEvent.FAILURE]
        assert second != first
