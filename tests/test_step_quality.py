"""Tests for step quality scoring (services/step_quality.py)."""

import pytest

from services.step_quality import (
    _compute_step_count_score,
    _compute_step_structure_score,
    _compute_step_temporal_score,
    _parse_step_time_to_seconds,
    _resolve_quality_reason_penalty,
    _resolve_quality_score,
)


class TestParseStepTime:
    def test_plain_seconds(self):
        assert _parse_step_time_to_seconds("12") == 12.0

    def test_mm_ss(self):
        assert _parse_step_time_to_seconds("01:30") == 90.0

    def test_hh_mm_ss(self):
        assert _parse_step_time_to_seconds("01:00:30") == 3630.0

    def test_fullwidth_colon(self):
        assert _parse_step_time_to_seconds("1：30") == 90.0

    def test_empty_returns_none(self):
        assert _parse_step_time_to_seconds("") is None

    def test_garbage_returns_none(self):
        assert _parse_step_time_to_seconds("abc") is None


class TestStructureScore:
    def test_empty_is_zero(self):
        assert _compute_step_structure_score([]) == 0.0

    def test_rich_steps_score_higher(self):
        rich = [{"title": "A clear title here", "description": "x" * 50, "time": "0:10"}]
        poor = [{"title": "", "description": "", "time": ""}]
        assert _compute_step_structure_score(rich) > _compute_step_structure_score(poor)

    def test_bounded_0_1(self):
        steps = [{"title": "t" * 100, "description": "d" * 100, "time": "0:01"}] * 5
        s = _compute_step_structure_score(steps)
        assert 0.0 <= s <= 1.0


class TestTemporalScore:
    def test_empty_zero(self):
        assert _compute_step_temporal_score([]) == 0.0

    def test_monotonic_times_score_well(self):
        steps = [{"time": f"0:{i:02d}"} for i in (5, 15, 25, 35, 45)]
        assert _compute_step_temporal_score(steps) > 0.4


class TestCountScore:
    def test_steps_ideal_range(self):
        assert _compute_step_count_score(5, "steps") == 1.0

    def test_zero_count(self):
        assert _compute_step_count_score(0, "steps") == 0.0

    def test_candidate_mode(self):
        assert _compute_step_count_score(4, "candidate_steps") == 0.94


class TestReasonPenalty:
    def test_empty_zero(self):
        assert _resolve_quality_reason_penalty("") == 0.0

    def test_failed_keyword(self):
        assert _resolve_quality_reason_penalty("something_failed_here") == 0.12

    def test_summary_keyword(self):
        assert _resolve_quality_reason_penalty("a_summary_thing") == 0.06


class TestResolveQualityScore:
    def test_blocked_notice_zero(self):
        assert _resolve_quality_score("blocked_notice", [{"title": "x"}], False) == 0.0

    def test_no_steps_zero(self):
        assert _resolve_quality_score("steps", [], False) == 0.0

    def test_steps_mode_in_range(self):
        steps = [{"title": f"Step {i}", "description": "do it", "time": f"0:{i*5:02d}", "source": "subtitle"} for i in range(1, 6)]
        score = _resolve_quality_score("steps", steps, False)
        assert 0.0 < score <= 0.98

    def test_fallback_lowers_score(self):
        steps = [{"title": f"S{i}", "description": "x", "time": f"0:{i*5:02d}", "source": "model"} for i in range(1, 6)]
        without = _resolve_quality_score("steps", steps, False)
        with_fb = _resolve_quality_score("steps", steps, True)
        assert with_fb < without
