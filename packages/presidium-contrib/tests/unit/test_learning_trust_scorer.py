from __future__ import annotations

import pytest

from presidium.model import TrustEvent, TrustTier
from presidium.trust import TrustScorer
from presidium_contrib.trust.scorer import LearningTrustScorer


class TestProtocol:
    def test_satisfies_trust_scorer(self) -> None:
        scorer = LearningTrustScorer()
        assert isinstance(scorer, TrustScorer)


class TestBasicScoring:
    def test_default_value(self) -> None:
        scorer = LearningTrustScorer()
        assert scorer.value == pytest.approx(0.5, abs=0.001)
        assert scorer.tier == TrustTier.STANDARD

    def test_success_increments(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value == pytest.approx(0.52, abs=0.01)

    def test_failure_decrements(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.FAILURE)
        assert scorer.value == pytest.approx(0.45, abs=0.01)

    def test_policy_violation_decrements_more(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.POLICY_VIOLATION)
        assert scorer.value == pytest.approx(0.40, abs=0.01)

    def test_clamped_at_bounds(self) -> None:
        scorer = LearningTrustScorer(initial_value=0.99)
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value <= 1.0

        scorer2 = LearningTrustScorer(initial_value=0.02)
        scorer2.record_event(TrustEvent.POLICY_VIOLATION)
        assert scorer2.value >= 0.0


class TestCustomWeights:
    def test_custom_weights_applied(self) -> None:
        scorer = LearningTrustScorer(weights={TrustEvent.SUCCESS: 0.10, TrustEvent.FAILURE: -0.20})
        scorer.record_event(TrustEvent.SUCCESS)
        assert scorer.value == pytest.approx(0.60, abs=0.01)

    def test_adjust_weights(self) -> None:
        scorer = LearningTrustScorer()
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
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.FAILURE)
        assert len(scorer.journal) == 2
        assert scorer.journal[0].event == TrustEvent.SUCCESS
        assert scorer.journal[1].event == TrustEvent.FAILURE

    def test_journal_captures_before_after(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.FAILURE)
        entry = scorer.journal[0]
        assert entry.value_before == pytest.approx(0.5, abs=0.01)
        assert entry.value_after == pytest.approx(0.45, abs=0.01)
        assert entry.tier_before == TrustTier.STANDARD
        assert entry.tier_after == TrustTier.STANDARD

    def test_set_value_recorded_as_human_override(self) -> None:
        scorer = LearningTrustScorer()
        scorer.set_value(0.9)
        assert len(scorer.journal) == 1
        assert scorer.journal[0].event == TrustEvent.HUMAN_OVERRIDE
        assert scorer.journal[0].context == {"set_value": 0.9}

    def test_context_passed_through(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.SUCCESS, context={"tool": "web_search"})
        assert scorer.journal[0].context == {"tool": "web_search"}

    def test_journal_returns_copy(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.SUCCESS)
        j = scorer.journal
        j.clear()
        assert len(scorer.journal) == 1


class TestLearning:
    def test_learns_from_override_after_harsh_penalty(self) -> None:
        # Failure penalty too harsh → human overrides trust higher
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)  # human says "that penalty was too harsh"

        old_failure_weight = scorer.weights[TrustEvent.FAILURE]
        scorer.learn_from_history(learning_rate=0.5)
        new_failure_weight = scorer.weights[TrustEvent.FAILURE]

        # Override raised trust → failure weight should become less negative
        assert new_failure_weight > old_failure_weight

    def test_learns_from_override_after_generous_reward(self) -> None:
        # Success reward too generous → human overrides trust lower
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.set_value(0.45)  # human says "that reward was too generous"

        old_success_weight = scorer.weights[TrustEvent.SUCCESS]
        scorer.learn_from_history(learning_rate=0.5)
        new_success_weight = scorer.weights[TrustEvent.SUCCESS]

        # Override lowered trust → success weight should decrease
        assert new_success_weight < old_success_weight

    def test_no_learning_without_overrides(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.SUCCESS)
        scorer.record_event(TrustEvent.FAILURE)
        old_weights = scorer.weights
        scorer.learn_from_history()
        assert scorer.weights == old_weights

    def test_returns_updated_weights(self) -> None:
        scorer = LearningTrustScorer()
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        result = scorer.learn_from_history()
        assert TrustEvent.FAILURE in result

    def test_skips_consecutive_overrides(self) -> None:
        scorer = LearningTrustScorer()
        scorer.set_value(0.3)
        scorer.set_value(0.6)  # consecutive override — nothing to learn from
        old_weights = scorer.weights
        scorer.learn_from_history()
        assert scorer.weights == old_weights

    def test_multiple_overrides_average(self) -> None:
        scorer = LearningTrustScorer()
        # Two failures, both followed by human raising trust
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.50)
        scorer.record_event(TrustEvent.FAILURE)
        scorer.set_value(0.48)

        scorer.learn_from_history(learning_rate=1.0)
        # Both overrides raised trust → failure weight should be less negative
        assert scorer.weights[TrustEvent.FAILURE] > -0.05
