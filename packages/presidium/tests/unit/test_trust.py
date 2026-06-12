from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from presidium.model import TrustEvent, TrustTier
from presidium.trust import (
    TIER_STANDARD_THRESHOLD,
    TIER_TRUSTED_THRESHOLD,
    LinearTrustScore,
    TrustScorer,
    tier_for_value,
)


class TestTierForValue:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1.0, TrustTier.TRUSTED),
            (0.7, TrustTier.TRUSTED),
            (0.71, TrustTier.TRUSTED),
            (0.69, TrustTier.STANDARD),
            (0.5, TrustTier.STANDARD),
            (0.3, TrustTier.STANDARD),
            (0.31, TrustTier.STANDARD),
            (0.29, TrustTier.RESTRICTED),
            (0.1, TrustTier.RESTRICTED),
            (0.0, TrustTier.RESTRICTED),
        ],
    )
    def test_tier_boundaries(self, value: float, expected: TrustTier) -> None:
        assert tier_for_value(value) == expected

    def test_thresholds_match_design_doc(self) -> None:
        assert TIER_TRUSTED_THRESHOLD == 0.7
        assert TIER_STANDARD_THRESHOLD == 0.3


class TestLinearTrustScoreProtocol:
    def test_satisfies_protocol(self) -> None:
        score = LinearTrustScore()
        assert isinstance(score, TrustScorer)


class TestLinearTrustScoreConstruction:
    def test_default_values(self) -> None:
        score = LinearTrustScore()
        assert score.value == pytest.approx(0.5, abs=0.001)
        assert score.tier == TrustTier.STANDARD

    def test_custom_initial(self) -> None:
        score = LinearTrustScore(initial_value=0.8)
        assert score.value == pytest.approx(0.8, abs=0.001)
        assert score.tier == TrustTier.TRUSTED

    def test_clamps_above_1(self) -> None:
        score = LinearTrustScore(initial_value=1.5)
        assert score.value <= 1.0

    def test_clamps_below_0(self) -> None:
        score = LinearTrustScore(initial_value=-0.5)
        assert score.value >= 0.0

    def test_last_updated_set_on_construction(self) -> None:
        before = datetime.now(UTC)
        score = LinearTrustScore()
        after = datetime.now(UTC)
        assert before <= score.last_updated <= after


class TestLinearTrustScoreEvents:
    def _make_score(self, value: float = 0.5) -> LinearTrustScore:
        now = datetime.now(UTC)
        return LinearTrustScore(initial_value=value, _now=now)

    def test_success_increments(self) -> None:
        score = self._make_score(0.5)
        score.record_event(TrustEvent.SUCCESS)
        assert score.value == pytest.approx(0.52, abs=0.01)

    def test_failure_decrements(self) -> None:
        score = self._make_score(0.5)
        score.record_event(TrustEvent.FAILURE)
        assert score.value == pytest.approx(0.45, abs=0.01)

    def test_policy_violation_decrements_more(self) -> None:
        score = self._make_score(0.5)
        score.record_event(TrustEvent.POLICY_VIOLATION)
        assert score.value == pytest.approx(0.40, abs=0.01)

    def test_capped_at_1(self) -> None:
        score = self._make_score(0.99)
        score.record_event(TrustEvent.SUCCESS)
        assert score.value <= 1.0

    def test_floored_at_0(self) -> None:
        score = self._make_score(0.02)
        score.record_event(TrustEvent.POLICY_VIOLATION)
        assert score.value >= 0.0

    def test_tier_transition_standard_to_trusted(self) -> None:
        score = self._make_score(0.69)
        assert score.tier == TrustTier.STANDARD
        score.record_event(TrustEvent.SUCCESS)
        assert score.value == pytest.approx(0.71, abs=0.01)
        assert score.tier == TrustTier.TRUSTED

    def test_tier_transition_standard_to_restricted(self) -> None:
        score = self._make_score(0.31)
        assert score.tier == TrustTier.STANDARD
        score.record_event(TrustEvent.FAILURE)
        assert score.value == pytest.approx(0.26, abs=0.01)
        assert score.tier == TrustTier.RESTRICTED

    def test_last_updated_changes_on_event(self) -> None:
        score = self._make_score(0.5)
        before = score.last_updated
        score.record_event(TrustEvent.SUCCESS)
        assert score.last_updated >= before

    def test_human_override_no_delta(self) -> None:
        score = self._make_score(0.5)
        score.record_event(TrustEvent.HUMAN_OVERRIDE)
        # HUMAN_OVERRIDE has no delta — value unchanged (modulo negligible decay)
        assert score.value == pytest.approx(0.5, abs=0.01)

    def test_set_value_for_human_override(self) -> None:
        score = self._make_score(0.5)
        score.set_value(0.9)
        assert score.value == pytest.approx(0.9, abs=0.001)
        assert score.tier == TrustTier.TRUSTED

    def test_set_value_clamps(self) -> None:
        score = self._make_score(0.5)
        score.set_value(1.5)
        assert score.value <= 1.0
        score.set_value(-1.0)
        assert score.value >= 0.0


class TestLinearTrustScoreDecay:
    def test_decay_over_time(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=10)
        score = LinearTrustScore(initial_value=0.5, _now=past)
        # After 10 hours at 0.01/hr decay: 0.5 - 0.1 = 0.4
        assert score.value == pytest.approx(0.4, abs=0.02)

    def test_no_decay_at_zero_elapsed(self) -> None:
        score = LinearTrustScore(initial_value=0.5)
        assert score.value == pytest.approx(0.5, abs=0.001)

    def test_decay_floors_at_zero(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=1000)
        score = LinearTrustScore(initial_value=0.5, _now=past)
        assert score.value == 0.0

    def test_custom_decay_rate(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=5)
        score = LinearTrustScore(initial_value=0.5, decay_rate=0.05, _now=past)
        # 0.5 - (0.05 * 5) = 0.25
        assert score.value == pytest.approx(0.25, abs=0.02)

    def test_decay_materializes_on_event(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=5)
        score = LinearTrustScore(initial_value=0.5, _now=past)
        # Before event: 0.5 - 0.05 = 0.45 (lazy decay)
        # SUCCESS materializes 0.45, then adds +0.02 = 0.47
        score.record_event(TrustEvent.SUCCESS)
        assert score.value == pytest.approx(0.47, abs=0.02)

    def test_success_resets_decay_clock(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=5)
        score = LinearTrustScore(initial_value=0.5, _now=past)
        score.record_event(TrustEvent.SUCCESS)
        # After SUCCESS, last_positive_signal is reset to now
        # so no additional decay should apply
        val_after_event = score.value
        assert score.value == pytest.approx(val_after_event, abs=0.001)

    def test_failure_does_not_reset_decay_clock(self) -> None:
        now = datetime.now(UTC)
        score = LinearTrustScore(initial_value=0.5, _now=now)
        score.record_event(TrustEvent.FAILURE)
        # FAILURE does not reset _last_positive_signal
        # so decay continues from original time
        assert score._last_positive_signal == now


class TestLinearTrustScoreTableDriven:
    @pytest.mark.parametrize(
        ("initial", "events", "expected_approx"),
        [
            (0.5, [], 0.5),
            (0.5, [TrustEvent.SUCCESS], 0.52),
            (0.5, [TrustEvent.FAILURE], 0.45),
            (0.5, [TrustEvent.POLICY_VIOLATION], 0.40),
            (0.5, [TrustEvent.SUCCESS, TrustEvent.SUCCESS], 0.54),
            (0.5, [TrustEvent.FAILURE, TrustEvent.FAILURE], 0.40),
            (0.0, [TrustEvent.SUCCESS], 0.02),
            (1.0, [TrustEvent.FAILURE], 0.95),
            (0.05, [TrustEvent.POLICY_VIOLATION], 0.0),
        ],
    )
    def test_event_sequences(
        self, initial: float, events: list[TrustEvent], expected_approx: float
    ) -> None:
        score = LinearTrustScore(initial_value=initial)
        for event in events:
            score.record_event(event)
        assert score.value == pytest.approx(expected_approx, abs=0.02)
