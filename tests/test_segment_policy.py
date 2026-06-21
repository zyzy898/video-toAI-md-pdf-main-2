"""Tests for video segment policy logic (services/segment_policy.py)."""

import pytest

from services.segment_policy import (
    _apply_video_segment_processing_guardrails,
    _build_segment_policy_reject_payload,
    _classify_video_segment_zone,
    _evaluate_batch_segment_policy,
    _format_duration_brief,
)


class TestClassifyZone:
    def test_standard(self):
        assert _classify_video_segment_zone(60.0, 10.0) == "standard"

    def test_long_by_size(self):
        assert _classify_video_segment_zone(60.0, 300.0) == "long"

    def test_super_long_by_duration(self):
        # > long max (45m) but <= super_long max (90m)
        assert _classify_video_segment_zone(50 * 60, 10.0) == "super_long"

    def test_trim_required_by_size(self):
        assert _classify_video_segment_zone(60.0, 600.0) == "trim_required"

    def test_trim_required_by_duration(self):
        assert _classify_video_segment_zone(100 * 60, 10.0) == "trim_required"

    def test_unknown_duration_uses_size(self):
        assert _classify_video_segment_zone(None, 10.0) == "standard"


class TestFormatDurationBrief:
    def test_unknown(self):
        assert _format_duration_brief(None) == "未知"
        assert _format_duration_brief(0) == "未知"

    def test_seconds(self):
        assert _format_duration_brief(45) == "45s"

    def test_minutes(self):
        assert _format_duration_brief(90) == "1m30s"

    def test_hours(self):
        assert _format_duration_brief(3700) == "1h01m"


class TestRejectPayload:
    def test_shape(self):
        policy = {"zone": "trim_required"}
        out = _build_segment_policy_reject_payload(policy, code="C", error_message="E")
        assert out == {"error": "E", "code": "C", "segment_policy": policy}


class TestGuardrails:
    def test_long_zone_disables_video_and_vision(self):
        uv, ws, mv, so, notes = _apply_video_segment_processing_guardrails(
            {"zone": "long"}, use_video=True, web_search=False, max_vision=5, summary_only=False
        )
        assert uv is False
        assert mv == 0
        assert notes  # explanatory notes present

    def test_super_long_forces_summary_only(self):
        uv, ws, mv, so, notes = _apply_video_segment_processing_guardrails(
            {"zone": "super_long"}, use_video=False, web_search=False, max_vision=0, summary_only=False
        )
        assert so is True

    def test_standard_zone_keeps_settings(self):
        uv, ws, mv, so, notes = _apply_video_segment_processing_guardrails(
            {"zone": "standard"}, use_video=False, web_search=False, max_vision=3, summary_only=False
        )
        # standard zone makes no zone-based downgrades (provider check may apply but use_video=False here)
        assert mv == 3
        assert so is False


class TestBatchEvaluation:
    def _policy(self, zone, filename="f.mp4", duration=60.0, size=10.0):
        return {
            "zone": zone,
            "filename": filename,
            "duration_seconds": duration,
            "duration_text": "1m",
            "file_size_mb": size,
        }

    def test_trim_required_blocks_batch(self):
        out = _evaluate_batch_segment_policy([self._policy("trim_required")])
        assert out["allowed"] is False
        assert out["code"] == "video_segment_trim_required"

    def test_super_long_blocks_batch(self):
        out = _evaluate_batch_segment_policy([self._policy("super_long")])
        assert out["allowed"] is False
        assert out["code"] == "video_segment_super_long_batch_not_allowed"

    def test_long_over_limit_blocks(self):
        policies = [self._policy("long") for _ in range(3)]
        out = _evaluate_batch_segment_policy(policies)
        assert out["allowed"] is False
        assert out["code"] == "video_segment_long_batch_limit"

    def test_standard_batch_allowed(self):
        out = _evaluate_batch_segment_policy([self._policy("standard")])
        assert out["allowed"] is True
        assert out["code"] == ""
